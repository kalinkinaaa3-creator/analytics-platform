"""Read existing CRM records; never query Bitrix from a dashboard request."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from bitrix24.models import (
    BitrixCrmDictionary, BitrixCrmField, BitrixDeal, BitrixDealCategory, BitrixLead,
    BitrixLeadAnalytics, BitrixManagerTracking, BitrixStageHistory, BitrixUser,
)
from bitrix24.services.dashboard_query import UNTRACKED_DEPARTMENT_NAME
from .deal_metrics import enrich_deal, stage_key


MOSCOW = ZoneInfo("Europe/Moscow")
DEFAULT_CATEGORIES = [0, 2, 5]  # Verified against the supplied category export.


def date_bounds(filters):
    return (datetime.combine(filters["date_start"], time.min, MOSCOW),
            datetime.combine(filters["date_end"] + timedelta(days=1), time.min, MOSCOW))


def references():
    categories = list(BitrixDealCategory.objects.filter(is_deleted=False).order_by("sort", "category_id").values("category_id", "name", "sort"))
    category_map = {row["category_id"]: row for row in categories}
    for category_id in BitrixDeal.objects.filter(is_deleted=False).order_by().values_list("category_id", flat=True).distinct():
        if category_id not in category_map:
            item = {"category_id": category_id, "name": f"Воронка #{category_id} (нет в справочнике)", "sort": 999999}
            category_map[category_id] = item
            categories.append(item)
    stages, lead_stages, sources = {}, [], []
    for row in BitrixCrmDictionary.objects.filter(is_deleted=False).values("entity_id", "status_id", "name", "sort", "semantics"):
        entity = row["entity_id"]
        if entity == "STATUS":
            lead_stages.append(row)
        elif entity == "SOURCE":
            sources.append({"source_id": row["status_id"], "source_name": row["name"]})
        elif entity == "DEAL_STAGE" or entity.startswith("DEAL_STAGE_"):
            try:
                category = 0 if entity == "DEAL_STAGE" else int(entity.removeprefix("DEAL_STAGE_"))
            except ValueError:
                continue
            stages[stage_key(category, row["status_id"])] = {
                **row, "key": stage_key(category, row["status_id"]), "category_id": category,
                "category_name": category_map.get(category, {}).get("name", str(category)),
                "category_sort": category_map.get(category, {}).get("sort") or 0,
            }
    tracking = {row["user_id"]: row for row in BitrixManagerTracking.objects.values("user_id", "manager_name", "department_name")}
    users = {row["user_id"]: row for row in BitrixUser.objects.filter(is_deleted=False).values("user_id", "full_name")}
    enum_fields = {}
    for field in BitrixCrmField.objects.filter(
        is_deleted=False,
        entity_type_id=2,
        field_code__in=("UF_CRM_69B904B3E0AD1", "UF_CRM_64254B7D4853D"),
    ).values("field_code", "raw_payload"):
        enum_fields[field["field_code"]] = {
            str(item.get("ID")): item.get("VALUE") or str(item.get("ID"))
            for item in (field["raw_payload"] or {}).get("items", [])
            if item.get("ID") is not None
        }
    return {"categories": categories, "category_map": category_map, "stages": stages,
            "lead_stages": sorted(lead_stages, key=lambda r: r["sort"] or 0),
            "sources": sources, "tracking": tracking, "users": users,
            "deal_types": enum_fields.get("UF_CRM_69B904B3E0AD1", {}),
            "activities": enum_fields.get("UF_CRM_64254B7D4853D", {})}


def manager_scope(query, filters, refs, manager_field):
    tracking = refs["tracking"]
    departments = filters.get("department_names", [])
    if departments:
        ids = [key for key, value in tracking.items() if value["department_name"] in departments]
        condition = Q(**{f"{manager_field}__in": ids})
        if UNTRACKED_DEPARTMENT_NAME in departments:
            condition |= ~Q(**{f"{manager_field}__in": list(tracking)})
        query = query.filter(condition)
    if filters.get("exclude_untracked_department", True):
        query = query.filter(**{f"{manager_field}__in": list(tracking)})
    if filters.get("manager_ids"):
        query = query.filter(**{f"{manager_field}__in": filters["manager_ids"]})
    return query


def histories(entity_type, ids):
    result = defaultdict(list)
    if ids:
        for row in BitrixStageHistory.objects.filter(entity_type_id=entity_type, entity_id__in=ids).values(
            "entity_id", "history_id", "category_id", "stage_id", "stage_semantic_id", "created_at"
        ).iterator(chunk_size=2000):
            result[row["entity_id"]].append(row)
    return result


def enrich_leads(rows):
    events = histories(1, [row["lead_id"] for row in rows])
    now = timezone.now()
    for row in rows:
        history = sorted(events.get(row["lead_id"], []), key=lambda e: (e["created_at"], e["history_id"]))
        visits = {}
        for index, event in enumerate(history):
            end = history[index + 1]["created_at"] if index + 1 < len(history) else now
            key = event["stage_id"]
            visits[key] = visits.get(key, 0) + max(0, (end - event["created_at"]).total_seconds() / 86400)
        visits.setdefault(row["status_id"], None)
        row["visited"] = set(visits)
        row["visit_days"] = visits
        row["history_missing"] = not history
        if row["source_created_at"]:
            row["source_created_at"] = row["source_created_at"].astimezone(MOSCOW)
    return rows


def enrich_rows(query, refs):
    rows = list(query.values("deal_id", "title", "category_id", "stage_id", "stage_semantic_id", "assigned_by_id",
                             "lead_id", "company_id", "source_created_at", "source_updated_at", "opportunity", "currency_id", "source_id", "raw_payload"))
    events = histories(2, [row["deal_id"] for row in rows])
    now = timezone.now()
    result = []
    for row in rows:
        user_id = row["assigned_by_id"]
        tracking = refs["tracking"].get(user_id, {})
        row["manager_name"] = refs["users"].get(user_id, {}).get("full_name") or tracking.get("manager_name") or "Менеджер не назначен"
        row["department_name"] = tracking.get("department_name", UNTRACKED_DEPARTMENT_NAME)
        row["category_name"] = refs["category_map"].get(row["category_id"], {}).get("name", str(row["category_id"]))
        raw = row.pop("raw_payload") or {}
        return_value = raw.get("isReturnCustomer", raw.get("IS_RETURN_CUSTOMER"))
        row["is_return_customer"] = return_value is True or str(return_value).upper() in ("Y", "TRUE", "1")
        row["deal_type_id"] = str(raw.get("UF_CRM_69B904B3E0AD1") or "")
        row["deal_type_name"] = refs["deal_types"].get(row["deal_type_id"], row["deal_type_id"])
        row["activity_id"] = str(raw.get("UF_CRM_64254B7D4853D") or "")
        row["activity_name"] = refs["activities"].get(row["activity_id"], row["activity_id"])
        row["source_name"] = next((item["source_name"] for item in refs["sources"] if item["source_id"] == row.get("source_id")), "")
        # Calendar grouping follows Moscow business dates, including UTC boundaries.
        if row["source_created_at"]:
            row["source_created_at"] = row["source_created_at"].astimezone(MOSCOW)
        result.append(enrich_deal(row, events.get(row["deal_id"], []), refs["stages"], now))
    return result


def deal_queryset(filters, refs, *, cohort=False):
    query = BitrixDeal.objects.filter(is_deleted=False)
    if filters.get("category_ids"):
        query = query.filter(category_id__in=filters["category_ids"])
    if not cohort:
        start, end = date_bounds(filters)
        query = query.filter(source_created_at__gte=start, source_created_at__lt=end)
        query = manager_scope(query, filters, refs, "assigned_by_id")
        if filters.get("stage_keys"):
            condition = Q(pk__in=[])
            for key in filters["stage_keys"]:
                category, stage = key.split(":", 1)
                condition |= Q(category_id=int(category), stage_id=stage)
            query = query.filter(condition)
    return query


def deal_rows(filters, refs):
    rows = enrich_rows(deal_queryset(filters, refs), refs)
    if filters.get("results"):
        rows = [row for row in rows if row["result"] in filters["results"]]
    return rows


def cohort_rows(filters, refs):
    start, end = date_bounds(filters)
    leads = BitrixLeadAnalytics.objects.filter(source_created_at__gte=start, source_created_at__lt=end)
    leads = leads.filter(lead_id__in=BitrixLead.objects.filter(is_deleted=False).values("lead_id"))
    leads = manager_scope(leads, filters, refs, "manager_id")
    if filters.get("source_ids"):
        leads = leads.filter(source_id__in=filters["source_ids"])
    deals = deal_queryset(filters, refs, cohort=True)
    if filters.get("category_ids"):
        # User-approved rule: selected-category leads OR leads with no active deals.
        leads = leads.filter(Q(lead_id__in=deals.values("lead_id")) | ~Q(lead_id__in=BitrixDeal.objects.filter(
            is_deleted=False, lead_id__isnull=False).exclude(lead_id=0).values("lead_id")))
    rows = list(leads.values("lead_id", "title", "source_created_at", "source_id", "source_name", "status_id",
                            "status_name", "dashboard_status", "manager_id", "manager_name", "department_name", "opportunity"))
    ids = [row["lead_id"] for row in rows]
    enrich_leads(rows)
    linked = enrich_rows(deals.filter(lead_id__in=ids), refs) if ids else []
    # Without a lead there is no lead cohort: list these separately by deal creation.
    standalone = enrich_rows(manager_scope(deals.exclude(lead_id__in=BitrixLead.objects.filter(
        is_deleted=False).values("lead_id")).filter(
        source_created_at__gte=start, source_created_at__lt=end), filters, refs, "assigned_by_id"), refs)
    return rows, linked, standalone


def filter_options(filters, refs):
    manager_filters = {**filters, "manager_ids": []}
    users = manager_scope(BitrixUser.objects.filter(is_deleted=False), manager_filters, refs, "user_id")
    selected = filters.get("category_ids")
    stages = [row for row in refs["stages"].values() if not selected or row["category_id"] in selected]
    return {"categories": refs["categories"], "default_category_ids": DEFAULT_CATEGORIES,
            "stages": sorted(stages, key=lambda r: (r["category_sort"], r["category_id"], r["sort"] or 0)),
            "departments": [{"department_name": name} for name in sorted({r["department_name"] for r in refs["tracking"].values()} | {UNTRACKED_DEPARTMENT_NAME})],
            "managers": [{"manager_id": r["user_id"], "manager_name": r["full_name"]} for r in users.values("user_id", "full_name")],
            "sources": sorted([*refs["sources"], {"source_id": "", "source_name": "Источник не указан"}], key=lambda row: row["source_name"])}
