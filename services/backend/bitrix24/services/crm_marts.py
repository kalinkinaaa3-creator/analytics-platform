"""Atomic, typed ClickHouse marts for CRM entities and lead/deal cohorts."""
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
REFS = "default.bitrix_crm_references"

COLUMNS = (
    "entity_type", "entity_id", "lead_id", "title", "source_created_at", "source_updated_at",
    "manager_id", "assigned_by_id", "manager_name", "department_name", "company_id",
    "category_id", "category_name", "stage_id", "stage_key", "stage_name", "result", "result_name",
    "status_id", "status_name", "dashboard_status", "source_id", "source_name",
    "opportunity", "amount", "currency_id", "closed_at", "cycle_days", "stage_days",
    "calculated_at", "speed_calculated_at", "processing_duration_days", "is_return_customer",
    "deal_type_id", "deal_type_name", "activity_id", "activity_name", "history_missing",
    "visit_stage_keys", "visit_days", "visit_semantics", "snapshot",
)
REF_COLUMNS = ("ref_type", "ref_key", "number_id", "name", "category_id", "sort", "semantics", "department_name", "snapshot")


class SnapshotChanged(RuntimeError):
    pass


class MartUnavailable(RuntimeError):
    pass


def create_table(client, name):
    client.execute(f"""CREATE TABLE {name} (
        entity_type LowCardinality(String), entity_id Int64, lead_id Int64, title String,
        source_created_at Nullable(DateTime64(3, 'Europe/Moscow')),
        source_updated_at Nullable(DateTime64(3, 'Europe/Moscow')),
        manager_id Int64, assigned_by_id Int64, manager_name String, department_name String, company_id Int64,
        category_id Int64, category_name String, stage_id String, stage_key String, stage_name String,
        result LowCardinality(String), result_name String, status_id String, status_name String,
        dashboard_status String, source_id String, source_name String,
        opportunity Decimal(20, 2), amount Decimal(20, 2), currency_id String,
        closed_at Nullable(DateTime64(3, 'Europe/Moscow')), cycle_days Nullable(Float64),
        stage_days Nullable(Float64), calculated_at DateTime64(3, 'Europe/Moscow'),
        speed_calculated_at Nullable(DateTime64(3, 'Europe/Moscow')),
        processing_duration_days Nullable(Float64), is_return_customer Nullable(UInt8),
        deal_type_id String, deal_type_name String, activity_id String, activity_name String,
        history_missing UInt8, visit_stage_keys Array(String), visit_days Array(Nullable(Float64)),
        visit_semantics Array(String), snapshot String
    ) ENGINE = MergeTree ORDER BY (entity_type, entity_id)""")


def create_ref_table(client, name):
    client.execute(f"""CREATE TABLE {name} (
        ref_type LowCardinality(String), ref_key String, number_id Int64, name String,
        category_id Int64, sort Int64, semantics String, department_name String, snapshot String
    ) ENGINE = MergeTree ORDER BY (ref_type, ref_key, number_id)""")


def reference_rows(refs, snapshot):
    rows = []
    def add(kind, key="", number=0, name="", category=0, sort=0, semantics="", department=""):
        rows.append((kind, str(key), int(number or 0), name or "", int(category or 0), int(sort or 0), semantics or "", department or "", snapshot))
    for row in refs["categories"]:
        add("category", row["category_id"], row["category_id"], row["name"], sort=row.get("sort"))
    for key, row in refs["stages"].items():
        add("deal_stage", key, name=row["name"], category=row["category_id"], sort=row.get("sort"), semantics=row.get("semantics"))
    for row in refs["lead_stages"]:
        add("lead_stage", row["status_id"], name=row["name"], sort=row.get("sort"), semantics=row.get("semantics"))
    for row in refs["sources"]:
        add("source", row["source_id"], name=row["source_name"])
    for number, row in refs["tracking"].items():
        add("tracking", number, number, row.get("manager_name"), department=row.get("department_name"))
    for number, row in refs["users"].items():
        add("user", number, number, row.get("full_name"))
    for key, name in refs.get("deal_types", {}).items():
        add("deal_type", key, name=name)
    for key, name in refs.get("activities", {}).items():
        add("activity", key, name=name)
    return rows


def storage_row(kind, row, snapshot, now):
    visits = row.get("visits") or {}
    keys = sorted((row.get("visited") or set()) if kind == "lead" else visits)
    days = ([row.get("visit_days", {}).get(key) for key in keys] if kind == "lead"
            else [visits[key].get("days") for key in keys])
    semantics = ([""] * len(keys) if kind == "lead"
                 else [visits[key].get("semantics") or "" for key in keys])
    manager_id = row.get("assigned_by_id", row.get("manager_id")) or 0
    values = {
        "entity_type": kind, "entity_id": row.get("deal_id", row.get("lead_id")) or 0,
        "lead_id": row.get("lead_id") or 0, "title": row.get("title") or "",
        "source_created_at": row.get("source_created_at"), "source_updated_at": row.get("source_updated_at"),
        "manager_id": manager_id, "assigned_by_id": row.get("assigned_by_id") or manager_id,
        "manager_name": row.get("manager_name") or "", "department_name": row.get("department_name") or "",
        "company_id": row.get("company_id") or 0, "category_id": row.get("category_id") or 0,
        "category_name": row.get("category_name") or "", "stage_id": row.get("stage_id") or "",
        "stage_key": row.get("stage_key") or "", "stage_name": row.get("stage_name") or "",
        "result": row.get("result") or "", "result_name": row.get("result_name") or "",
        "status_id": row.get("status_id") or "", "status_name": row.get("status_name") or "",
        "dashboard_status": row.get("dashboard_status") or "", "source_id": row.get("source_id") or "",
        "source_name": row.get("source_name") or "",
        "opportunity": Decimal(str(row.get("opportunity") or 0)),
        "amount": Decimal(str(row.get("amount", row.get("opportunity")) or 0)),
        "currency_id": row.get("currency_id") or "", "closed_at": row.get("closed_at"),
        "cycle_days": row.get("cycle_days"), "stage_days": row.get("stage_days"),
        "calculated_at": row.get("calculated_at") or now,
        "speed_calculated_at": row.get("speed_calculated_at"),
        "processing_duration_days": row.get("processing_duration_days"),
        "is_return_customer": row.get("is_return_customer"), "deal_type_id": row.get("deal_type_id") or "",
        "deal_type_name": row.get("deal_type_name") or "", "activity_id": row.get("activity_id") or "",
        "activity_name": row.get("activity_name") or "", "history_missing": int(bool(row.get("history_missing"))),
        "visit_stage_keys": keys, "visit_days": days, "visit_semantics": semantics, "snapshot": snapshot,
    }
    return tuple(values[column] for column in COLUMNS)


def recreate_views(client):
    client.execute(f"DROP VIEW IF EXISTS {CYCLE}")
    client.execute(f"DROP VIEW IF EXISTS {DEALS}")
    client.execute(f"CREATE VIEW {DEALS} AS SELECT * FROM {TABLE} WHERE entity_type = 'deal'")
    client.execute(f"""CREATE VIEW {CYCLE} AS SELECT
        l.entity_id lead_id, l.source_created_at lead_created_at, l.manager_id lead_manager_id,
        l.department_name lead_department_name, l.source_id lead_source_id, l.title lead_title,
        d.entity_id deal_id, d.title deal_title, d.category_id, d.amount deal_amount,
        d.result deal_result, d.closed_at deal_closed_at, l.snapshot
        FROM (SELECT * FROM {TABLE} WHERE entity_type = 'lead') l
        LEFT ALL JOIN {DEALS} d ON d.lead_id = l.entity_id""")


def publish(*, chunk_size=1000):
    client = get_clickhouse_client()
    staging = f"{TABLE}_staging_{uuid4().hex[:12]}"
    ref_staging = f"{REFS}_staging_{uuid4().hex[:12]}"
    backup = f"{TABLE}_backup_{uuid4().hex[:12]}"
    ref_backup = f"{REFS}_backup_{uuid4().hex[:12]}"
    snapshot, now = uuid4().hex, timezone.now()
    create_table(client, staging)
    create_ref_table(client, ref_staging)
    count = 0
    try:
        with transaction.atomic():
            from django.db import connection
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            refs = source.references()
            client.execute(f"INSERT INTO {ref_staging} ({', '.join(REF_COLUMNS)}) VALUES", reference_rows(refs, snapshot))

            def write(kind, rows):
                nonlocal count
                values = [storage_row(kind, row, snapshot, now) for row in rows]
                if values:
                    client.execute(f"INSERT INTO {staging} ({', '.join(COLUMNS)}) VALUES", values)
                    count += len(values)

            leads = BitrixLeadAnalytics.objects.filter(
                lead_id__in=BitrixLead.objects.filter(is_deleted=False).values("lead_id")
            )
            fields = ("lead_id", "title", "source_created_at", "source_id", "source_name", "status_id",
                      "status_name", "dashboard_status", "manager_id", "manager_name", "department_name", "opportunity")
            pending = []
            for row in leads.order_by("lead_id").values(*fields).iterator(chunk_size=chunk_size):
                pending.append(row)
                if len(pending) >= chunk_size:
                    write("lead", source.enrich_leads(pending)); pending = []
            write("lead", source.enrich_leads(pending))
            pending = []
            ids = BitrixDeal.objects.filter(is_deleted=False).order_by("deal_id").values_list("deal_id", flat=True)
            for deal_id in ids.iterator(chunk_size=chunk_size):
                pending.append(deal_id)
                if len(pending) >= chunk_size:
                    write("deal", source.enrich_rows(BitrixDeal.objects.filter(deal_id__in=pending), refs)); pending = []
            write("deal", source.enrich_rows(BitrixDeal.objects.filter(deal_id__in=pending), refs))
        if client.execute(f"SELECT count() FROM {staging}")[0][0] != count:
            raise RuntimeError("CRM snapshot row count mismatch")
        if client.execute(f"SELECT count() FROM {ref_staging}")[0][0] != len(reference_rows(refs, snapshot)):
            raise RuntimeError("CRM reference snapshot row count mismatch")
        # Existing views depend on the old table schema (including payload),
        # so remove them before replacing the physical table.
        client.execute(f"DROP VIEW IF EXISTS {CYCLE}")
        client.execute(f"DROP VIEW IF EXISTS {DEALS}")
        entity_exists = client.execute(f"EXISTS TABLE {TABLE}")[0][0]
        refs_exist = client.execute(f"EXISTS TABLE {REFS}")[0][0]
        if entity_exists and refs_exist:
            client.execute(f"RENAME TABLE {TABLE} TO {backup}, {staging} TO {TABLE}, {REFS} TO {ref_backup}, {ref_staging} TO {REFS}")
            client.execute(f"DROP TABLE {backup}")
            client.execute(f"DROP TABLE {ref_backup}")
        elif entity_exists:
            client.execute(f"RENAME TABLE {TABLE} TO {backup}, {staging} TO {TABLE}, {ref_staging} TO {REFS}")
            client.execute(f"DROP TABLE {backup}")
        else:
            client.execute(f"RENAME TABLE {staging} TO {TABLE}, {ref_staging} TO {REFS}")
        recreate_views(client)
    finally:
        client.execute(f"DROP TABLE IF EXISTS {staging}")
        client.execute(f"DROP TABLE IF EXISTS {ref_staging}")
        client.execute(f"DROP TABLE IF EXISTS {backup}")
        client.execute(f"DROP TABLE IF EXISTS {ref_backup}")
    return count


class MartReader:
    def __init__(self, client=None):
        self.client = client or get_clickhouse_client()
        if not self.client.execute("EXISTS TABLE " + TABLE)[0][0] or not self.client.execute("EXISTS TABLE " + REFS)[0][0]:
            raise MartUnavailable("CRM ClickHouse snapshot is not published")
        rows = self.client.execute(f"SELECT DISTINCT snapshot FROM {TABLE}")
        ref_rows = self.client.execute(f"SELECT {', '.join(REF_COLUMNS)} FROM {REFS} ORDER BY ref_type, ref_key, number_id")
        if len(rows) != 1 or not ref_rows or {row[-1] for row in ref_rows} != {rows[0][0]}:
            raise MartUnavailable("CRM ClickHouse snapshot is not published")
        self.snapshot = rows[0][0]
        self.refs = self.restore_refs(ref_rows)

    @staticmethod
    def restore_refs(values):
        refs = {"categories": [], "category_map": {}, "stages": {}, "lead_stages": [], "sources": [],
                "tracking": {}, "users": {}, "deal_types": {}, "activities": {}}
        for value in values:
            row = dict(zip(REF_COLUMNS, value)); kind = row["ref_type"]
            if kind == "category":
                item = {"category_id": row["number_id"], "name": row["name"], "sort": row["sort"]}
                refs["categories"].append(item); refs["category_map"][row["number_id"]] = item
            elif kind == "deal_stage":
                category = refs["category_map"].get(row["category_id"], {})
                refs["stages"][row["ref_key"]] = {"key": row["ref_key"], "status_id": row["ref_key"].split(":", 1)[-1],
                    "name": row["name"], "category_id": row["category_id"], "category_name": category.get("name", str(row["category_id"])),
                    "category_sort": category.get("sort", 0), "sort": row["sort"], "semantics": row["semantics"]}
            elif kind == "lead_stage":
                refs["lead_stages"].append({"status_id": row["ref_key"], "name": row["name"], "sort": row["sort"], "semantics": row["semantics"]})
            elif kind == "source": refs["sources"].append({"source_id": row["ref_key"], "source_name": row["name"]})
            elif kind == "tracking": refs["tracking"][row["number_id"]] = {"user_id": row["number_id"], "manager_name": row["name"], "department_name": row["department_name"]}
            elif kind == "user": refs["users"][row["number_id"]] = {"user_id": row["number_id"], "full_name": row["name"]}
            elif kind == "deal_type": refs["deal_types"][row["ref_key"]] = row["name"]
            elif kind == "activity": refs["activities"][row["ref_key"]] = row["name"]
        refs["categories"].sort(key=lambda row: (row["sort"], row["category_id"]))
        refs["lead_stages"].sort(key=lambda row: row["sort"])
        return refs

    @staticmethod
    def restore(values):
        row = dict(zip(COLUMNS, values))
        row["deal_id"] = row["entity_id"] if row["entity_type"] == "deal" else None
        keys, days, semantics = row.pop("visit_stage_keys"), row.pop("visit_days"), row.pop("visit_semantics")
        row["visited"] = set(keys)
        if row["entity_type"] == "deal":
            row["visits"] = {key: {"days": days[index], "semantics": semantics[index]} for index, key in enumerate(keys)}
        else:
            row["visit_days"] = {key: days[index] for index, key in enumerate(keys)}
        row["amount"], row["opportunity"] = float(row["amount"]), float(row["opportunity"])
        row["is_return_customer"] = None if row["is_return_customer"] is None else bool(row["is_return_customer"])
        row["history_missing"] = bool(row["history_missing"])
        return row

    def select(self, entity_type, parts=(), args=None):
        args = {**(args or {}), "entity_type": entity_type}
        sql = f"SELECT {', '.join(COLUMNS)} FROM {TABLE} WHERE entity_type = %(entity_type)s"
        if parts:
            sql += " AND " + " AND ".join(parts)
        return [self.restore(row) for row in self.client.execute(sql, args)]

    def check(self):
        entity = self.client.execute(f"SELECT DISTINCT snapshot FROM {TABLE}")
        refs = self.client.execute(f"SELECT DISTINCT snapshot FROM {REFS}")
        if entity != [(self.snapshot,)] or refs != [(self.snapshot,)]:
            raise SnapshotChanged("CRM snapshot changed during the request")

    def conditions(self, filters):
        start, end = source.date_bounds(filters)
        parts, args = ["source_created_at >= %(start)s", "source_created_at < %(end)s"], {"start": start, "end": end}
        tracking = self.refs["tracking"]
        departments = filters.get("department_names", [])
        if departments:
            ids = tuple(key for key, value in tracking.items() if value["department_name"] in departments)
            args["departments"] = ids or (-1,)
            condition = "manager_id IN %(departments)s"
            if source.UNTRACKED_DEPARTMENT_NAME in departments:
                args["tracked"] = tuple(tracking) or (-1,)
                condition = f"({condition} OR manager_id NOT IN %(tracked)s)"
            parts.append(condition)
        if filters.get("exclude_untracked_department", True):
            args["tracked"] = tuple(tracking) or (-1,); parts.append("manager_id IN %(tracked)s")
        for field, column in (("manager_ids", "manager_id"), ("source_ids", "source_id")):
            if filters.get(field):
                parts.append(f"{column} IN %({field})s"); args[field] = tuple(filters[field])
        return parts, args

    def deals(self, filters):
        parts, args = self.conditions(filters)
        for field, column in (("category_ids", "category_id"), ("stage_keys", "stage_key"), ("results", "result")):
            if filters.get(field):
                parts.append(f"{column} IN %({field})s"); args[field] = tuple(filters[field])
        return self.select("deal", parts, args)

    def cohort(self, filters, *, include_standalone=True):
        parts, args = self.conditions(filters)
        leads = self.select("lead", parts, args)
        lead_ids = {row["lead_id"] for row in leads}
        linked = self.select("deal", ["lead_id IN %(lead_ids)s"], {"lead_ids": tuple(lead_ids) or (-1,)})
        categories = set(filters.get("category_ids", []))
        deals = [row for row in linked if not categories or row["category_id"] in categories]
        all_linked = {row["lead_id"] for row in linked if row["lead_id"]}
        selected = {row["lead_id"] for row in deals}
        leads = [row for row in leads if row["lead_id"] in selected or row["lead_id"] not in all_linked]
        if not include_standalone:
            return leads, deals, []
        deal_parts, deal_args = self.conditions(filters)
        deal_parts.append(f"(lead_id = 0 OR lead_id NOT IN (SELECT entity_id FROM {TABLE} WHERE entity_type = 'lead'))")
        standalone = self.select("deal", deal_parts, deal_args)
        if categories:
            standalone = [row for row in standalone if row["category_id"] in categories]
        return leads, deals, standalone

    def options(self, filters):
        refs, tracking = self.refs, self.refs["tracking"]
        users = []
        for key, user in refs["users"].items():
            department = tracking.get(key, {}).get("department_name", source.UNTRACKED_DEPARTMENT_NAME)
            if filters.get("exclude_untracked_department", True) and key not in tracking: continue
            if filters.get("department_names") and department not in filters["department_names"]: continue
            users.append({"manager_id": key, "manager_name": user["full_name"]})
        stages = [row for row in refs["stages"].values() if not filters.get("category_ids") or row["category_id"] in filters["category_ids"]]
        return {"categories": refs["categories"], "default_category_ids": source.DEFAULT_CATEGORIES,
                "stages": sorted(stages, key=lambda row: (row["category_sort"], row["category_id"], row["sort"] or 0)),
                "departments": [{"department_name": name} for name in sorted({row["department_name"] for row in tracking.values()} | {source.UNTRACKED_DEPARTMENT_NAME})],
                "managers": users,
                "sources": sorted([*refs["sources"], {"source_id": "", "source_name": "Источник не указан"}], key=lambda row: row["source_name"])}
