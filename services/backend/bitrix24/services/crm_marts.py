"""One atomic CRM snapshot, exposed as deal and lead/deal cohort marts.

PostgreSQL is read only during publication. Dashboard requests read ClickHouse.
Typed columns support filtering; payload retains observed stage visits and labels.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from analytics.clickhouse.client import get_clickhouse_client
from bitrix24.models import BitrixDeal, BitrixLead, BitrixLeadAnalytics
from . import deal_repository as source

TABLE = "default.bitrix_crm_entities"
DEALS = "default.bitrix_deal_analytics"
CYCLE = "default.bitrix_full_cycle_analytics"


class SnapshotChanged(RuntimeError):
    pass


class MartUnavailable(RuntimeError):
    pass


def encode(value):
    def default(item):
        if isinstance(item, (date, datetime)):
            return {"__datetime__": item.isoformat()}
        if isinstance(item, Decimal):
            return {"__decimal__": str(item)}
        if isinstance(item, set):
            return {"__set__": sorted(item)}
        raise TypeError(type(item).__name__)
    return json.dumps(value, default=default, ensure_ascii=False, separators=(",", ":"))


def decode(value):
    def hook(item):
        if set(item) == {"__datetime__"}:
            return datetime.fromisoformat(item["__datetime__"])
        if set(item) == {"__decimal__"}:
            return Decimal(item["__decimal__"])
        if set(item) == {"__set__"}:
            return set(item["__set__"])
        return item
    return json.loads(value, object_hook=hook)


def create_table(client, name):
    client.execute(f"""CREATE TABLE IF NOT EXISTS {name} (
        entity_type LowCardinality(String), entity_id Int64, lead_id Int64,
        source_created_at Nullable(DateTime64(3, 'Europe/Moscow')),
        manager_id Int64, department_name String, category_id Int64,
        stage_key String, result LowCardinality(String), source_id String,
        amount Decimal(20, 2), closed_at Nullable(DateTime64(3, 'Europe/Moscow')),
        cycle_days Nullable(Float64), stage_days Nullable(Float64),
        snapshot String, calculated_at DateTime64(3, 'Europe/Moscow'), payload String
    ) ENGINE = MergeTree ORDER BY (entity_type, entity_id)""")


def storage_row(kind, row, snapshot, now):
    return (kind, row.get("deal_id", row.get("lead_id", 0)) or 0,
            row.get("lead_id") or 0, row.get("source_created_at"),
            row.get("assigned_by_id", row.get("manager_id")) or 0,
            row.get("department_name", ""), row.get("category_id") or 0,
            row.get("stage_key", ""), row.get("result", ""), row.get("source_id", ""),
            Decimal(str(row.get("opportunity") or 0)), row.get("closed_at"),
            row.get("cycle_days"), row.get("stage_days"), snapshot, now, encode(row))


def publish(*, chunk_size=1000):
    """Called under the CRM refresh lock. No external API calls."""
    client = get_clickhouse_client()
    staging = f"{TABLE}_staging_{uuid4().hex[:12]}"
    snapshot, now = uuid4().hex, timezone.now()
    create_table(client, TABLE)
    create_table(client, staging)
    count = 0
    try:
        # A consistent source snapshot also protects against concurrent raw imports.
        with transaction.atomic():
            from django.db import connection
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            refs = source.references()
            client.execute(f"INSERT INTO {staging} VALUES", [storage_row("refs", refs, snapshot, now)])
            leads = BitrixLeadAnalytics.objects.filter(lead_id__in=BitrixLead.objects.filter(is_deleted=False).values("lead_id"))
            pending = []
            def write(kind, rows):
                nonlocal count
                values = [storage_row(kind, row, snapshot, now) for row in rows]
                if values:
                    client.execute(f"INSERT INTO {staging} VALUES", values)
                    count += len(values)
            fields = ("lead_id", "title", "source_created_at", "source_id", "source_name", "status_id",
                      "status_name", "dashboard_status", "manager_id", "manager_name", "department_name", "opportunity")
            def lead_batch(rows):
                write("lead", source.enrich_leads(rows))
            for row in leads.order_by("lead_id").values(*fields).iterator(chunk_size=chunk_size):
                pending.append(row)
                if len(pending) >= chunk_size:
                    lead_batch(pending)
                    pending = []
            lead_batch(pending)
            pending = []
            for deal_id in BitrixDeal.objects.filter(is_deleted=False).order_by("deal_id").values_list("deal_id", flat=True).iterator(chunk_size=chunk_size):
                pending.append(deal_id)
                if len(pending) >= chunk_size:
                    write("deal", source.enrich_rows(BitrixDeal.objects.filter(deal_id__in=pending), refs))
                    pending = []
            write("deal", source.enrich_rows(BitrixDeal.objects.filter(deal_id__in=pending), refs))
        actual = client.execute(f"SELECT count() FROM {staging}")[0][0]
        if actual != count + 1:
            raise RuntimeError("CRM snapshot row count mismatch")
        # Both views share one physical snapshot: there is no half-published pair.
        client.execute(f"""CREATE VIEW IF NOT EXISTS {DEALS} AS
            SELECT entity_id AS deal_id, JSONExtractString(payload, 'title') AS title,
                   JSONExtractString(payload, 'manager_name') AS manager_name,
                   JSONExtractString(payload, 'category_name') AS category_name,
                   JSONExtractString(payload, 'stage_id') AS stage_id,
                   JSONExtractString(payload, 'stage_name') AS stage_name,
                   JSONExtractString(payload, 'currency_id') AS currency_id, *
            FROM {TABLE} WHERE entity_type = 'deal'""")
        client.execute(f"""CREATE VIEW IF NOT EXISTS {CYCLE} AS
            SELECT l.entity_id AS lead_id, l.source_created_at AS lead_created_at,
                   l.manager_id AS lead_manager_id, l.department_name AS lead_department_name,
                   l.source_id AS lead_source_id, l.payload AS lead_payload,
                   JSONExtractString(l.payload, 'title') AS lead_title,
                   d.deal_id AS deal_id, d.title AS deal_title, d.category_id AS category_id,
                   d.amount AS deal_amount, d.result AS deal_result,
                   d.closed_at AS deal_closed_at, d.payload AS deal_payload,
                   l.snapshot AS snapshot
            FROM (SELECT * FROM {TABLE} WHERE entity_type = 'lead') l
            LEFT ALL JOIN {DEALS} d ON d.lead_id = l.entity_id""")
        client.execute(f"EXCHANGE TABLES {TABLE} AND {staging}")
    finally:
        client.execute(f"DROP TABLE IF EXISTS {staging}")
    return count


class MartReader:
    def __init__(self, client=None):
        self.client = client or get_clickhouse_client()
        if not self.client.execute("EXISTS TABLE " + TABLE)[0][0]:
            raise MartUnavailable("CRM ClickHouse snapshot is not published")
        rows = self.client.execute(f"SELECT snapshot, payload FROM {TABLE} WHERE entity_type = 'refs'")
        if len(rows) != 1:
            raise MartUnavailable("CRM ClickHouse snapshot is not published")
        self.snapshot, payload = rows[0]
        self.refs = decode(payload)
        for key in ("category_map", "tracking", "users"):
            self.refs[key] = {int(k): v for k, v in self.refs[key].items()}

    def check(self):
        rows = self.client.execute(f"SELECT snapshot FROM {TABLE} WHERE entity_type = 'refs'")
        if rows != [(self.snapshot,)]:
            raise SnapshotChanged("CRM snapshot changed during the request")

    def conditions(self, filters, *, lead=False):
        start, end = source.date_bounds(filters)
        parts, args = ["source_created_at >= %(start)s", "source_created_at < %(end)s"], {"start": start, "end": end}
        tracking = self.refs["tracking"]
        departments = filters.get("department_names", [])
        if departments:
            ids = tuple(k for k, v in tracking.items() if v["department_name"] in departments)
            args["departments"] = ids or (-1,)
            condition = "manager_id IN %(departments)s"
            if source.UNTRACKED_DEPARTMENT_NAME in departments:
                args["tracked"] = tuple(tracking) or (-1,)
                condition = f"({condition} OR manager_id NOT IN %(tracked)s)"
            parts.append(condition)
        if filters.get("exclude_untracked_department", True):
            args["tracked"] = tuple(tracking) or (-1,)
            parts.append("manager_id IN %(tracked)s")
        for field, column in (("manager_ids", "manager_id"), ("source_ids", "source_id")):
            if filters.get(field) and (field != "source_ids" or lead):
                parts.append(f"{column} IN %({field})s")
                args[field] = tuple(filters[field])
        return parts, args

    def deals(self, filters):
        parts, args = self.conditions(filters)
        for field, column in (("category_ids", "category_id"), ("stage_keys", "stage_key"), ("results", "result")):
            if filters.get(field):
                parts.append(f"{column} IN %({field})s")
                args[field] = tuple(filters[field])
        return [decode(r[0]) for r in self.client.execute(f"SELECT payload FROM {DEALS} WHERE " + " AND ".join(parts), args)]

    def cohort(self, filters, *, include_standalone=True):
        parts, args = self.conditions(filters, lead=True)
        # Filter the lead side first; dates of linked deals are deliberately unrestricted.
        where = " AND ".join(parts)
        rows = self.client.execute(f"""SELECT lead_payload, deal_payload FROM {CYCLE}
            WHERE lead_id IN (SELECT entity_id FROM {TABLE} WHERE entity_type = 'lead' AND {where})""", args)
        categories = set(filters.get("category_ids", []))
        leads, deals, all_linked, selected = {}, [], set(), set()
        for lead_payload, deal_payload in rows:
            lead = decode(lead_payload)
            leads[lead["lead_id"]] = lead
            if deal_payload:
                deal = decode(deal_payload)
                all_linked.add(lead["lead_id"])
                if not categories or deal["category_id"] in categories:
                    deals.append(deal)
                    selected.add(lead["lead_id"])
        leads = [r for key, r in leads.items() if key in selected or key not in all_linked]
        if not include_standalone:
            return leads, deals, []
        parts, args = self.conditions(filters)
        parts.append(f"lead_id NOT IN (SELECT entity_id FROM {TABLE} WHERE entity_type = 'lead')")
        if categories:
            parts.append("category_id IN %(categories)s")
            args["categories"] = tuple(categories)
        standalone = [decode(r[0]) for r in self.client.execute(f"SELECT payload FROM {DEALS} WHERE " + " AND ".join(parts), args)]
        return leads, deals, standalone

    def options(self, filters):
        refs, tracking = self.refs, self.refs["tracking"]
        users = []
        for key, user in refs["users"].items():
            department = tracking.get(key, {}).get("department_name", source.UNTRACKED_DEPARTMENT_NAME)
            if filters.get("exclude_untracked_department", True) and key not in tracking:
                continue
            if filters.get("department_names") and department not in filters["department_names"]:
                continue
            users.append({"manager_id": key, "manager_name": user["full_name"]})
        stages = [r for r in refs["stages"].values() if not filters.get("category_ids") or r["category_id"] in filters["category_ids"]]
        return {"categories": refs["categories"], "default_category_ids": source.DEFAULT_CATEGORIES,
                "stages": sorted(stages, key=lambda r: (r["category_sort"], r["category_id"], r["sort"] or 0)),
                "departments": [{"department_name": name} for name in sorted({r["department_name"] for r in tracking.values()} | {source.UNTRACKED_DEPARTMENT_NAME})],
                "managers": users, "sources": refs["sources"]}
