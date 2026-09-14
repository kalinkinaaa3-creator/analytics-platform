"""Atomic, typed ClickHouse mart for CRM deals."""
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from django.utils.functional import cached_property

from analytics.clickhouse.client import get_clickhouse_client
from bitrix24.models import BitrixDeal
from bitrix24.cache import get_dashboard_cache, set_dashboard_cache
from . import deal_repository as source

TABLE = "default.bitrix_deal_analytics"
# Public table name also imported by the lead-generation report.
DEALS = TABLE
LEGACY_TABLE = "default.bitrix_crm_entities"
LEGACY_CYCLE = "default.bitrix_full_cycle_analytics"
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
LEGACY_COLUMNS = COLUMNS
COLUMNS = (*[column for column in COLUMNS if column not in ("entity_type", "cycle_days", "stage_days", "visit_stage_keys", "visit_days", "visit_semantics")], "category_sort", "stage_sort", "stage_semantics", "manager_tracked")

REF_COLUMNS = ("ref_type", "ref_key", "number_id", "name", "category_id", "sort", "semantics", "department_name", "snapshot")


class SnapshotChanged(RuntimeError):
    pass


class MartUnavailable(RuntimeError):
    pass


def create_table(client, name, snapshot):
    client.execute(f"""CREATE TABLE {name} (
        entity_id Int64, lead_id Int64, title String,
        source_created_at Nullable(DateTime64(3, 'Europe/Moscow')),
        source_updated_at Nullable(DateTime64(3, 'Europe/Moscow')),
        manager_id Int64, assigned_by_id Int64, manager_name String, department_name String, company_id Int64,
        category_id Int64, category_name String, stage_id String, stage_key String, stage_name String,
        result LowCardinality(String), result_name String, status_id String, status_name String,
        dashboard_status String, source_id String, source_name String,
        opportunity Decimal(20, 2), amount Decimal(20, 2), currency_id String,
        closed_at Nullable(DateTime64(3, 'Europe/Moscow')), calculated_at DateTime64(3, 'Europe/Moscow'),
        speed_calculated_at Nullable(DateTime64(3, 'Europe/Moscow')),
        processing_duration_days Nullable(Float64), is_return_customer Nullable(UInt8),
        deal_type_id String, deal_type_name String, activity_id String, activity_name String,
        history_missing UInt8, snapshot String,
        category_sort Int64, stage_sort Int64, stage_semantics String, manager_tracked UInt8
    ) ENGINE = MergeTree ORDER BY entity_id COMMENT '{snapshot}'""")


def reference_rows(refs, snapshot):
    rows = []
    def add(kind, key="", number=0, name="", category=0, sort=0, semantics="", department=""):
        rows.append((kind, str(key), int(number or 0), name or "", int(category or 0), int(sort or 0), semantics or "", department or "", snapshot))
    for row in refs["categories"]:
        add("category", row["category_id"], row["category_id"], row["name"], sort=row.get("sort"))
    for key, row in refs["stages"].items():
        add("deal_stage", key, name=row["name"], category=row["category_id"], sort=row.get("sort"), semantics=row.get("semantics"))
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


def storage_row(kind, row, snapshot, now, refs):
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
        "calculated_at": row.get("calculated_at") or now,
        "speed_calculated_at": row.get("speed_calculated_at"),
        "processing_duration_days": row.get("processing_duration_days"),
        "is_return_customer": row.get("is_return_customer"), "deal_type_id": row.get("deal_type_id") or "",
        "deal_type_name": row.get("deal_type_name") or "", "activity_id": row.get("activity_id") or "",
        "activity_name": row.get("activity_name") or "", "history_missing": int(bool(row.get("history_missing"))),
        "snapshot": snapshot,
        "category_sort": refs["category_map"].get(row.get("category_id"), {}).get("sort") or 0,
        "stage_sort": refs["stages"].get(row.get("stage_key"), {}).get("sort") or 0,
        "stage_semantics": refs["stages"].get(row.get("stage_key"), {}).get("semantics") or "",
        "manager_tracked": int(manager_id in refs["tracking"]),
    }
    return tuple(values[column] for column in COLUMNS)


def table_metadata(client, table=TABLE):
    database, name = table.split(".", 1)
    rows = client.execute(
        "SELECT engine, comment FROM system.tables WHERE database = %(database)s AND name = %(name)s",
        {"database": database, "name": name},
    )
    return rows[0] if rows else None


def publish(*, chunk_size=1000):
    client = get_clickhouse_client()
    staging = f"{TABLE}_staging_{uuid4().hex[:12]}"
    backup = f"{TABLE}_backup_{uuid4().hex[:12]}"
    snapshot, now = uuid4().hex, timezone.now()
    create_table(client, staging, snapshot)
    count = 0
    try:
        with transaction.atomic():
            from django.db import connection
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            refs = source.references()

            def write(rows):
                nonlocal count
                values = [storage_row("deal", row, snapshot, now, refs) for row in rows]
                if values:
                    client.execute(f"INSERT INTO {staging} ({', '.join(COLUMNS)}) VALUES", values)
                    count += len(values)

            pending = []
            ids = BitrixDeal.objects.filter(is_deleted=False).order_by("deal_id").values_list("deal_id", flat=True)
            for deal_id in ids.iterator(chunk_size=chunk_size):
                pending.append(deal_id)
                if len(pending) >= chunk_size:
                    write(source.enrich_rows(BitrixDeal.objects.filter(deal_id__in=pending), refs))
                    pending = []
            write(source.enrich_rows(BitrixDeal.objects.filter(deal_id__in=pending), refs))
        if client.execute(f"SELECT count() FROM {staging}")[0][0] != count:
            raise RuntimeError("CRM snapshot row count mismatch")
        metadata = table_metadata(client)
        if metadata is None:
            client.execute(f"RENAME TABLE {staging} TO {TABLE}")
        elif metadata[0] == "View":
            # One-time conversion: retain the legacy physical tables for rollback.
            # Readers can use them throughout the initial publication.
            client.execute(f"RENAME TABLE {TABLE} TO {backup}, {staging} TO {TABLE}")
            client.execute(f"DROP VIEW IF EXISTS {backup}")
        else:
            client.execute(f"EXCHANGE TABLES {TABLE} AND {staging}")
    finally:
        client.execute(f"DROP TABLE IF EXISTS {staging}")
    return count


class MartReader:
    def __init__(self, client=None):
        self.client = client or get_clickhouse_client()
        metadata = table_metadata(self.client)
        self.legacy = metadata is None or metadata[0] == "View"
        self.table = LEGACY_TABLE if self.legacy else TABLE
        if self.legacy:
            if not self.client.execute("EXISTS TABLE " + LEGACY_TABLE)[0][0] or not self.client.execute("EXISTS TABLE " + REFS)[0][0]:
                raise MartUnavailable("CRM ClickHouse snapshot is not published")
            rows = self.client.execute(f"SELECT DISTINCT snapshot FROM {LEGACY_TABLE}")
            ref_rows = self.client.execute(f"SELECT {', '.join(REF_COLUMNS)} FROM {REFS} ORDER BY ref_type, ref_key, number_id")
            if len(rows) != 1 or not ref_rows or {row[-1] for row in ref_rows} != {rows[0][0]}:
                raise MartUnavailable("CRM ClickHouse snapshot is not published")
            self.snapshot = rows[0][0]
            self.refs = self.restore_refs(ref_rows)
        else:
            # Table metadata also identifies a valid, completely empty snapshot.
            self.snapshot = metadata[1]
            if not self.snapshot:
                raise MartUnavailable("CRM ClickHouse snapshot is not published")

    @cached_property
    def refs(self):
        key = {"deal_references": 1, "snapshot": self.snapshot}
        cached = get_dashboard_cache(key)
        if cached is not None:
            return cached
        refs = self.published_references()
        self.check()
        set_dashboard_cache(key, refs)
        return refs

    def published_references(self):
        refs = {"categories": [], "category_map": {}, "stages": {}, "sources": [],
                "tracking": {}, "users": {}, "deal_types": {}, "activities": {}}
        def distinct(columns):
            return self.client.execute(f"SELECT DISTINCT {columns} FROM {TABLE}")
        for key, name, sort in distinct("category_id, category_name, category_sort"):
            item = {"category_id": key, "name": name, "sort": sort}
            refs["categories"].append(item)
            refs["category_map"][key] = item
        for key, stage_id, name, category, category_name, category_sort, sort, semantics in distinct(
            "stage_key, stage_id, stage_name, category_id, category_name, category_sort, stage_sort, stage_semantics"
        ):
            refs["stages"][key] = {"key": key, "status_id": stage_id, "name": name,
                "category_id": category, "category_name": category_name, "category_sort": category_sort,
                "sort": sort, "semantics": semantics}
        for key, name, department, tracked in distinct("manager_id, manager_name, department_name, manager_tracked"):
            refs["users"][key] = {"user_id": key, "full_name": name}
            if tracked:
                refs["tracking"][key] = {"user_id": key, "manager_name": name, "department_name": department}
        refs["sources"] = [{"source_id": key, "source_name": name} for key, name in distinct("source_id, source_name") if key]
        refs["categories"].sort(key=lambda row: (row["sort"], row["category_id"]))
        return refs

    @staticmethod
    def restore_refs(values):
        refs = {"categories": [], "category_map": {}, "stages": {}, "sources": [],
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
            elif kind == "source": refs["sources"].append({"source_id": row["ref_key"], "source_name": row["name"]})
            elif kind == "tracking": refs["tracking"][row["number_id"]] = {"user_id": row["number_id"], "manager_name": row["name"], "department_name": row["department_name"]}
            elif kind == "user": refs["users"][row["number_id"]] = {"user_id": row["number_id"], "full_name": row["name"]}
            elif kind == "deal_type": refs["deal_types"][row["ref_key"]] = row["name"]
            elif kind == "activity": refs["activities"][row["ref_key"]] = row["name"]
        refs["categories"].sort(key=lambda row: (row["sort"], row["category_id"]))
        return refs

    @staticmethod
    def restore(values, columns=COLUMNS):
        row = dict(zip(columns, values))
        for field in ("entity_type", "cycle_days", "stage_days"):
            row.pop(field, None)
        row["deal_id"] = row["entity_id"]
        for field in ("visit_stage_keys", "visit_days", "visit_semantics"):
            row.pop(field, None)
        row["amount"], row["opportunity"] = float(row["amount"]), float(row["opportunity"])
        row["is_return_customer"] = None if row["is_return_customer"] is None else bool(row["is_return_customer"])
        row["history_missing"] = bool(row["history_missing"])
        return row

    def select(self, parts=(), args=None):
        args = dict(args or {})
        columns = tuple(column for column in LEGACY_COLUMNS if column not in ("cycle_days", "stage_days", "visit_stage_keys", "visit_days", "visit_semantics")) if self.legacy else COLUMNS
        sql = f"SELECT {', '.join(columns)} FROM {self.table} WHERE 1"
        if self.legacy:
            sql += " AND entity_type = 'deal'"
        if parts:
            sql += " AND " + " AND ".join(parts)
        return [self.restore(row, columns) for row in self.client.execute(sql, args)]

    def check(self):
        if self.legacy:
            entity = self.client.execute(f"SELECT DISTINCT snapshot FROM {LEGACY_TABLE}")
            refs = self.client.execute(f"SELECT DISTINCT snapshot FROM {REFS}")
            if entity != [(self.snapshot,)] or refs != [(self.snapshot,)]:
                raise SnapshotChanged("CRM snapshot changed during the request")
        elif table_metadata(self.client) != ("MergeTree", self.snapshot):
            raise SnapshotChanged("CRM snapshot changed during the request")

    def conditions(self, filters):
        start, end = source.date_bounds(filters)
        parts, args = ["source_created_at >= %(start)s", "source_created_at < %(end)s"], {"start": start, "end": end}
        tracking = self.refs["tracking"]
        if "tracked_manager_ids" in filters:
            tracked_ids = set(filters["tracked_manager_ids"])
            tracking = {key: row for key, row in tracking.items() if key in tracked_ids}
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
        if filters.get("lead_link") == "linked":
            parts.append("lead_id > 0")
        for field, column in (("manager_ids", "manager_id"), ("source_ids", "source_id")):
            if filters.get(field):
                parts.append(f"{column} IN %({field})s"); args[field] = tuple(filters[field])
        return parts, args

    def deal_conditions(self, filters):
        parts, args = self.conditions(filters)
        for field, column in (("category_ids", "category_id"), ("stage_keys", "stage_key"), ("results", "result")):
            if filters.get(field):
                parts.append(f"{column} IN %({field})s"); args[field] = tuple(filters[field])
        return parts, args

    def deals(self, filters):
        parts, args = self.deal_conditions(filters)
        return self.select(parts, args)

    def options(self, filters, *, faceted=True, personal_manager_ids=None):
        refs, tracking = self.refs, self.refs["tracking"]
        if "tracked_manager_ids" in filters:
            tracked_ids = set(filters["tracked_manager_ids"])
            tracking = {key: row for key, row in tracking.items() if key in tracked_ids}
        if not faceted:
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

        def available(ignore, column):
            scoped = {**filters, ignore: []}
            if ignore == "department_names":
                scoped["exclude_untracked_department"] = False
            elif personal_manager_ids is not None:
                scoped["manager_ids"] = list(personal_manager_ids) or [-1]
                scoped["exclude_untracked_department"] = False
            parts, args = self.conditions(scoped)
            for field, deal_column in (("category_ids", "category_id"), ("stage_keys", "stage_key"), ("results", "result")):
                if field != ignore and scoped.get(field):
                    parts.append(f"{deal_column} IN %({field})s")
                    args[field] = tuple(scoped[field])
            sql = f"SELECT DISTINCT {column} FROM {getattr(self, 'table', TABLE)} WHERE 1"
            if getattr(self, "legacy", False):
                sql += " AND entity_type = 'deal'"
            if parts:
                sql += " AND " + " AND ".join(parts)
            return {row[0] for row in self.client.execute(sql, args)}

        manager_ids = available("manager_ids", "manager_id") | set(filters.get("manager_ids", []))
        category_ids = available("category_ids", "category_id") | set(filters.get("category_ids", []))
        stage_keys = available("stage_keys", "stage_key") | set(filters.get("stage_keys", []))
        source_ids = available("source_ids", "source_id") | set(filters.get("source_ids", []))
        results = available("results", "result") | set(filters.get("results", []))
        department_manager_ids = available("department_names", "manager_id")
        department_names = {tracking[key]["department_name"] if key in tracking else source.UNTRACKED_DEPARTMENT_NAME for key in department_manager_ids}
        # Match lead facets: only departments present in the effective manager scope.
        # Echoing requested names here resurrects hidden personal defaults.
        users = [{"manager_id": key, "manager_name": refs["users"].get(key, {}).get("full_name") or str(key)} for key in manager_ids if key]
        stages = [row for key, row in refs["stages"].items() if key in stage_keys]
        categories = [row for row in refs["categories"] if row["category_id"] in category_ids]
        sources = [row for row in refs["sources"] if row["source_id"] in source_ids]
        if "" in source_ids:
            sources.append({"source_id": "", "source_name": "Источник не указан"})
        return {"categories": categories, "default_category_ids": source.DEFAULT_CATEGORIES,
                "stages": sorted(stages, key=lambda row: (row["category_sort"], row["category_id"], row["sort"] or 0)),
                "departments": [{"department_name": name} for name in sorted(department_names)],
                "managers": sorted(users, key=lambda row: row["manager_name"]),
                "sources": sorted(sources, key=lambda row: row["source_name"]),
                "results": [{"id": key, "name": name} for key, name in (("S", "Успешные"), ("F", "Проигранные"), ("P", "В работе"), ("?", "Статус не определён")) if key in results]}
