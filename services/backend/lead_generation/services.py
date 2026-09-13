from datetime import date, timedelta

from bitrix24.services.refresh import refresh_state as bitrix_refresh_state
from bitrix24.models import BitrixSyncState
from context_analytics.models import ContextRefreshRun
from context_analytics.services.refresh import latest_state as context_refresh_state
from django.core.cache import cache
from django.utils import timezone

from .cache import REPORT_TIMEOUT, SOURCE_OPTIONS_TIMEOUT, invalidate_lead_generation_cache, report_cache_key
from .clickhouse import MART_TABLE, ensure_mart_table
from .models import LeadGenerationPlan, LeadGenerationSourcePreference
from bitrix24.services.crm_marts import DEALS as BITRIX_DEALS_TABLE


MIN_WEEK = date(2024, 12, 30)


def current_week_start(today=None):
    today = today or timezone.localdate()
    return today - timedelta(days=today.weekday())


def normalize_filters(params):
    start = date.fromisoformat(params.get("week_from") or MIN_WEEK.isoformat())
    end = date.fromisoformat(params.get("week_to") or current_week_start().isoformat())
    if start.weekday() or end.weekday():
        raise ValueError("Период можно задавать только понедельниками.")
    if start < MIN_WEEK:
        raise ValueError("Первая доступная неделя начинается 30.12.2024.")
    if end < start:
        raise ValueError("Конечная неделя не может быть раньше начальной.")
    return {"week_from": start, "week_to": end, "include_select_market": str(params.get("include_select_market", "true")).lower() != "false"}


def _dict_rows(client, sql, params=None):
    rows, columns = client.execute(sql, params or {}, with_column_types=True)
    names = [column[0] for column in columns]
    return [dict(zip(names, row)) for row in rows]


def _number(value):
    return float(value or 0)


def _facts(filters):
    client = ensure_mart_table()
    params = {"date_from": filters["week_from"], "date_to": filters["week_to"] + timedelta(days=6)}
    rows = _dict_rows(client, f"""
        SELECT week_start, toFloat64(direct_cost) direct_cost,
               total_leads, target_leads, additional_apm_leads,
               non_target_leads, unprocessed_leads,
               toFloat64(lead_opportunity) opportunity
        FROM {MART_TABLE}
        WHERE row_kind = 'total'
          AND week_start BETWEEN %(date_from)s AND %(date_to)s
        ORDER BY week_start
    """, params)
    result = {}
    for row in rows:
        row["target_leads"] = int(row["target_leads"] or 0) + (
            int(row["additional_apm_leads"] or 0) if filters["include_select_market"] else 0
        )
        result[row["week_start"]] = row
    return result


def _plan_rows(filters):
    return {row.week_start: row for row in LeadGenerationPlan.objects.filter(week_start__range=(filters["week_from"], filters["week_to"]))}


def _week_range(filters):
    current = filters["week_from"]
    while current <= filters["week_to"]:
        yield current
        current += timedelta(days=7)


def _plan_report(filters, *, include_funnels=False):
    facts = _facts(filters)
    successful_deals, funnel_amounts, deal_funnels = _successful_deal_amounts(filters)
    plans = _plan_rows(filters)
    rows = []
    for week in _week_range(filters):
        plan = plans.get(week)
        fact = facts.get(week, {})
        budget = _number(plan.budget_vat) if plan else 0
        plan_cpl = _number(plan.target_lead_price) if plan else 0
        plan_leads = _number(plan.target_leads) if plan else 0
        revenue_plan = _number(plan.revenue_plan) if plan else 0
        cost = _number(fact.get("direct_cost"))
        total = int(fact.get("total_leads") or 0)
        target = int(fact.get("target_leads") or 0)
        row = {
            "week_start": week.isoformat(), "budget_vat": budget,
            "target_lead_price": plan_cpl, "planned_target_leads": plan_leads,
            "average_revenue_per_lead": revenue_plan / plan_leads if plan_leads else None,
            "revenue_plan": revenue_plan,
            "budget_revenue_share": budget * 100 / revenue_plan if revenue_plan else None,
            "direct_cost": cost, "cost_delta": budget - cost,
            "total_leads": total, "target_leads": target,
            "non_target_leads": int(fact.get("non_target_leads") or 0),
            "unprocessed_leads": int(fact.get("unprocessed_leads") or 0),
            "target_conversion": target * 100 / total if total else None,
            "target_delta": target - plan_leads,
            "actual_target_cpl": cost / target if target else None,
            "target_cpl_delta": plan_cpl - cost / target if target else None,
            "lead_opportunity": _number(fact.get("opportunity")),
            "successful_deal_amount": _number(successful_deals.get(week)),
        }
        row.update({item["key"]: _number(funnel_amounts.get(week, {}).get(item["key"])) for item in deal_funnels})
        rows.append(row)
    return (rows, deal_funnels) if include_funnels else rows


def _successful_deal_amounts(filters):
    """All successful RUB deals grouped by the deal's own creation week."""
    client = ensure_mart_table()
    if not client.execute(f"EXISTS TABLE {BITRIX_DEALS_TABLE}")[0][0]:
        return {}, {}, []
    rows = client.execute(f"""
        SELECT toStartOfWeek(source_created_at, 1) AS week_start,
               category_id, any(category_name) AS category_name, sum(amount) AS amount
        FROM {BITRIX_DEALS_TABLE}
        WHERE result = 'S'
          AND currency_id = 'RUB'
          AND source_created_at >= %(date_from)s
          AND source_created_at < %(date_to)s
        GROUP BY week_start, category_id
    """, {"date_from": filters["week_from"], "date_to": filters["week_to"] + timedelta(days=7)})
    totals, by_week, categories = {}, {}, {}
    for week, category_id, name, amount in rows:
        key = f"successful_deal_category_{category_id}"
        amount = amount or 0
        totals[week] = totals.get(week, 0) + amount
        weekly = by_week.setdefault(week, {})
        weekly[key] = weekly.get(key, 0) + amount
        category = categories.setdefault(key, {"key": key, "category_id": category_id,
            "name": name or f"Воронка #{category_id}", "total": 0})
        category["total"] += amount
    columns = [{"key": item["key"], "category_id": item["category_id"],
                "name": f"Сумма успешных сделок: {item['name']}, руб"}
               for item in sorted(categories.values(), key=lambda item: (-item["total"], item["name"], item["category_id"]))
               if item["total"] != 0]
    return totals, by_week, columns


def _source_report(filters, preference=None):
    client = ensure_mart_table()
    selected = [str(value) for value in (preference.source_ids if preference else [])]
    params = {"date_from": filters["week_from"], "date_to": filters["week_to"] + timedelta(days=6)}
    facts = _dict_rows(client, f"""
        SELECT week_start, source_id, source_name, total_leads, target_leads,
               additional_apm_leads, non_target_leads, unprocessed_leads
        FROM {MART_TABLE}
        WHERE row_kind = 'source'
          AND week_start BETWEEN %(date_from)s AND %(date_to)s
        ORDER BY week_start, source_name
    """, params)
    for item in facts:
        item["target_leads"] = int(item["target_leads"] or 0) + (
            int(item["additional_apm_leads"] or 0) if filters["include_select_market"] else 0
        )
    by_week = {}
    source_names = {}
    for item in facts:
        source_names[str(item["source_id"])] = item["source_name"]
        by_week.setdefault(item["week_start"], []).append(item)
    plans = _plan_rows(filters)
    rows = []
    for week in _week_range(filters):
        items = by_week.get(week, [])
        plan = plans.get(week)
        total = sum(int(item["total_leads"] or 0) for item in items)
        target_total = sum(int(item["target_leads"] or 0) for item in items)
        non_target = sum(int(item["non_target_leads"] or 0) for item in items)
        unprocessed = sum(int(item["unprocessed_leads"] or 0) for item in items)
        by_source = {str(item["source_id"]): item for item in items}
        selected_target = sum(int(by_source.get(source_id, {}).get("target_leads") or 0) for source_id in selected)
        other_items = [item for item in items if str(item["source_id"]) not in selected]
        other_target = sum(int(item["target_leads"] or 0) for item in other_items)
        planned = _number(plan.target_leads) if plan else 0
        breakdown = {}
        for source_id in selected:
            item = by_source.get(source_id, {})
            source_total, source_target = int(item.get("total_leads") or 0), int(item.get("target_leads") or 0)
            breakdown[source_id] = {"total": source_total, "target": source_target, "conversion": source_target * 100 / source_total if source_total else None}
        other_total = sum(int(item["total_leads"] or 0) for item in other_items)
        breakdown["__other__"] = {"total": other_total, "target": other_target, "conversion": other_target * 100 / other_total if other_total else None}
        rows.append({
            "week_start": week.isoformat(), "planned_target_leads": planned,
            "total_leads": total, "target_leads": target_total,
            "non_target_leads": non_target, "unprocessed_leads": unprocessed,
            "target_conversion": target_total * 100 / total if total else None,
            "target_delta": target_total - planned,
            "target_deviation": (target_total - planned) * 100 / planned if planned else None,
            "associated_target_leads": selected_target,
            "associated_share": selected_target * 100 / target_total if target_total else None,
            "other_target_leads": other_target,
            "other_share": other_target * 100 / target_total if target_total else None,
            "sources": breakdown,
        })
    all_source_names = {item["id"]: item["name"] for item in source_options()}
    configured = [{"id": source_id, "name": source_names.get(source_id, all_source_names.get(source_id, source_id))} for source_id in selected]
    configured.append({"id": "__other__", "name": "Прочие источники"})
    return rows, configured


def source_options():
    key = "leadgen:source-options:v1"
    cached = cache.get(key)
    if cached is not None:
        return cached
    client = ensure_mart_table()
    result = [{"id": str(row[0]), "name": row[1] or str(row[0])} for row in client.execute(f"""
        SELECT source_id, any(source_name) name
        FROM {MART_TABLE}
        WHERE row_kind = 'source'
        GROUP BY source_id ORDER BY name
    """)]
    cache.set(key, result, timeout=SOURCE_OPTIONS_TIMEOUT)
    return result


def build_report(page, filters, user):
    preference = None
    preference_version = ""
    if page == "sources":
        preference = LeadGenerationSourcePreference.objects.filter(user=user).first()
        preference_version = preference.updated_at.isoformat() if preference else "empty"
    key = report_cache_key(
        page, filters, user_id=getattr(user, "id", None),
        preference_version=preference_version,
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    if page == "plan":
        rows, deal_funnels = _plan_report(filters, include_funnels=True)
        sources = []
        from .revenue import add_revenue
        revenue_directions = add_revenue(rows, filters)
    elif page == "sources":
        rows, sources = _source_report(filters, preference=preference)
    else:
        raise ValueError("Неизвестная вкладка отчёта.")
    result = {"rows": rows, "sources": sources, "filters": {**filters, "week_from": filters["week_from"].isoformat(), "week_to": filters["week_to"].isoformat()}}
    if page == "plan":
        result["revenue_directions"] = revenue_directions
        result["deal_funnels"] = deal_funnels
    cache.set(key, result, timeout=REPORT_TIMEOUT)
    return result


def update_source_preference(user, source_ids):
    available = {item["id"] for item in source_options()}
    normalized = list(dict.fromkeys(str(value) for value in source_ids if str(value) in available))
    preference, _ = LeadGenerationSourcePreference.objects.update_or_create(user=user, defaults={"source_ids": normalized})
    invalidate_lead_generation_cache()
    return preference.source_ids


def refresh_information():
    bitrix = bitrix_refresh_state()
    bitrix_state = BitrixSyncState.objects.filter(entity="leads").first()
    direct = context_refresh_state()
    direct_success = ContextRefreshRun.objects.filter(status=ContextRefreshRun.Status.SUCCESS, finished_at__isnull=False).first()
    client = ensure_mart_table()
    mart = client.execute(f"SELECT maxOrNull(mart_built_at), count() FROM {MART_TABLE}")[0]
    return {
        "bitrix": {**bitrix, "last_success_at": bitrix_state.last_success_at if bitrix_state else None},
        "direct": {**direct, "last_success_at": direct_success.finished_at if direct_success else None},
        "mart": {"last_success_at": mart[0], "rows": int(mart[1])},
    }
