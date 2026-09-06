from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from context_analytics.models import ContextCampaign
from context_analytics.services.clickhouse import (
    CRITERIA_GOAL_TABLE, CRITERIA_TABLE, GOAL_TABLE, PERFORMANCE_TABLE, VISITOR_TABLE,
    replace_range, staged_tables,
)
from seo_analytics.models import SeoGoal
from context_analytics.services.metrika import ContextMetrikaClient


BASE_DIMENSIONS = ["Date", "CampaignId", "CampaignName", "CampaignType", "AdGroupId", "AdGroupName",
                   "AdNetworkType", "Device", "Gender", "Age"]
BASE_METRICS = ["Impressions", "Clicks", "Cost", "Sessions", "Bounces", "AvgPageviews",
                "AvgImpressionPosition", "AvgClickPosition"]
CRITERIA_DIMENSIONS = ["Date", "CampaignId", "CampaignName", "CampaignType", "AdGroupId", "AdGroupName",
                       "AdNetworkType", "CriterionId", "Criterion", "CriterionType"]


def _int(row, key):
    try:
        return max(0, int(round(float(row.get(key) or 0))))
    except (TypeError, ValueError):
        return 0


def _nullable_int(row, key):
    value = row.get(key)
    if value in (None, "", "--"):
        return None
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return None


def _float(row, key):
    try:
        return float(row.get(key) or 0) if row.get(key) != "--" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _nullable_float(row, key):
    value = row.get(key)
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(row, key="Cost"):
    try:
        return Decimal(str(row.get(key) or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _text(row, key):
    return str(row.get(key) or "Не определено")


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Некорректная дата в источнике контекстной рекламы: {value!r}")


def _goal_batches(goals, size=10):
    for index in range(0, len(goals), size):
        yield goals[index:index + size]


def _metrika_dimension(row, index, *, prefer_id=False):
    dimensions = row.get("dimensions") or []
    item = dimensions[index] if index < len(dimensions) else {}
    if prefer_id:
        return str((item or {}).get("id") or (item or {}).get("name") or "0")
    return str((item or {}).get("name") or (item or {}).get("id") or "Не определено")


def _visitor_rows(date_from, date_to, loaded_at, progress=None):
    payload = ContextMetrikaClient(
        progress=(lambda report_key, _status: progress(report_key)) if progress else None
    ).table_all(
        report_key="context.visitors",
        date1=str(date_from), date2=str(date_to),
        dimensions=["ym:s:date", "ym:s:<attribution>DirectClickOrder"],
        metrics=["ym:s:users", "ym:s:newUsers"],
        attribution="cross_device_last_significant",
    )
    rows = []
    for row in payload.get("data") or []:
        campaign = _metrika_dimension(row, 1, prefer_id=True)
        try:
            campaign_id = int(campaign)
        except (TypeError, ValueError):
            continue
        metrics = list(row.get("metrics") or []) + [0, 0]
        rows.append((_date_value(_metrika_dimension(row, 0)), campaign_id,
                     max(0, int(round(float(metrics[0] or 0)))),
                     max(0, int(round(float(metrics[1] or 0)))), loaded_at))
    return rows


def refresh_warehouse(direct, date_from, date_to, *, staged_target=None, sync_campaigns=True, progress=None):
    loaded_at = timezone.localtime()
    campaigns = direct.campaigns() if sync_campaigns else []
    received = []
    for item in campaigns:
        external_id = int(item["Id"])
        received.append(external_id)
        ContextCampaign.objects.update_or_create(external_id=external_id, defaults={
            "name": item.get("Name") or str(external_id), "campaign_type": item.get("Type") or "",
            "status": item.get("Status") or "", "state": item.get("State") or "",
            "start_date": item.get("StartDate") or None, "is_available": True,
            "source_updated_at": loaded_at,
        })
    if sync_campaigns:
        ContextCampaign.objects.exclude(external_id__in=received).update(is_available=False)
    if progress:
        progress("campaigns")

    base_source = direct.report(report_key="performance", date_from=date_from, date_to=date_to,
                                fields=BASE_DIMENSIONS + BASE_METRICS,
                                progress=(lambda attempt, _status: progress(f"performance:attempt-{attempt}")) if progress else None)
    base_rows = [(
        _date_value(row["Date"]), _int(row, "CampaignId"), _text(row, "CampaignName"), _text(row, "CampaignType"),
        _int(row, "AdGroupId"), _text(row, "AdGroupName"), _text(row, "AdNetworkType"), _text(row, "Device"),
        _text(row, "Gender"), _text(row, "Age"), _int(row, "Impressions"), _int(row, "Clicks"),
        _money(row), _nullable_int(row, "Sessions"), _nullable_int(row, "Bounces"), _float(row, "AvgPageviews"),
        _nullable_float(row, "AvgImpressionPosition"), _nullable_float(row, "AvgClickPosition"), loaded_at,
    ) for row in base_source]
    if progress:
        progress("performance")

    criteria_source = direct.report(report_key="criteria", date_from=date_from, date_to=date_to,
                                    fields=CRITERIA_DIMENSIONS + BASE_METRICS,
                                    progress=(lambda attempt, _status: progress(f"criteria:attempt-{attempt}")) if progress else None)
    criteria_rows = [(
        _date_value(row["Date"]), _int(row, "CampaignId"), _text(row, "CampaignName"), _text(row, "CampaignType"),
        _int(row, "AdGroupId"), _text(row, "AdGroupName"), _text(row, "AdNetworkType"), _int(row, "CriterionId"),
        _text(row, "Criterion"), _text(row, "CriterionType"), _int(row, "Impressions"),
        _int(row, "Clicks"), _money(row), _nullable_int(row, "Sessions"), _nullable_int(row, "Bounces"),
        _float(row, "AvgPageviews"), _nullable_float(row, "AvgImpressionPosition"),
        _nullable_float(row, "AvgClickPosition"), loaded_at,
    ) for row in criteria_source]
    if progress:
        progress("criteria")

    goals = list(SeoGoal.objects.filter(is_available=True).order_by("position", "id"))
    goal_rows, criteria_goal_rows = [], []
    for batch in _goal_batches(goals):
        ids = [goal.external_id for goal in batch]
        names = {goal.external_id: goal.name for goal in batch}
        for row in direct.report(report_key="performance_goals", date_from=date_from, date_to=date_to,
                                 fields=BASE_DIMENSIONS + ["Conversions"], goals=ids,
                                 progress=(lambda attempt, _status: progress(f"performance_goals:attempt-{attempt}")) if progress else None):
            for goal_id in ids:
                value = _int(row, f"Conversions_{goal_id}_LSCCD")
                if value:
                    goal_rows.append((_date_value(row["Date"]), _int(row, "CampaignId"), _int(row, "AdGroupId"),
                                      _text(row, "Device"), _text(row, "Gender"), _text(row, "Age"),
                                      goal_id, names[goal_id], value, loaded_at))
        if progress:
            progress("performance_goals")
        for row in direct.report(report_key="criteria_goals", date_from=date_from, date_to=date_to,
                                 fields=CRITERIA_DIMENSIONS + ["Conversions"], goals=ids,
                                 progress=(lambda attempt, _status: progress(f"criteria_goals:attempt-{attempt}")) if progress else None):
            for goal_id in ids:
                value = _int(row, f"Conversions_{goal_id}_LSCCD")
                if value:
                    criteria_goal_rows.append((_date_value(row["Date"]), _int(row, "CampaignId"), _int(row, "AdGroupId"),
                                               _int(row, "CriterionId"), _text(row, "CriterionType"),
                                               goal_id, names[goal_id], value, loaded_at))
        if progress:
            progress("criteria_goals")
    visitor_rows = _visitor_rows(date_from, date_to, loaded_at, progress=progress)
    if progress:
        progress("visitors")

    def write_rows(ch, tables):
        replace_range(ch, tables[PERFORMANCE_TABLE], date_from, date_to, base_rows,
                      ("date","campaign_id","campaign_name","campaign_type","ad_group_id","ad_group_name",
                       "ad_network_type","device","gender","age","impressions","clicks","cost","sessions","bounces",
                       "avg_pageviews","avg_impression_position","avg_click_position","loaded_at"))
        replace_range(ch, tables[GOAL_TABLE], date_from, date_to, goal_rows,
                      ("date","campaign_id","ad_group_id","device","gender","age","goal_id","goal_name",
                       "conversions","loaded_at"))
        replace_range(ch, tables[CRITERIA_TABLE], date_from, date_to, criteria_rows,
                      ("date","campaign_id","campaign_name","campaign_type","ad_group_id","ad_group_name",
                       "ad_network_type","criterion_id","criterion","criterion_type","impressions","clicks","cost","sessions",
                       "bounces","avg_pageviews","avg_impression_position","avg_click_position","loaded_at"))
        replace_range(ch, tables[CRITERIA_GOAL_TABLE], date_from, date_to, criteria_goal_rows,
                      ("date","campaign_id","ad_group_id","criterion_id","criterion_type","goal_id","goal_name",
                       "conversions","loaded_at"))
        replace_range(ch, tables[VISITOR_TABLE], date_from, date_to, visitor_rows,
                      ("date","campaign_id","users","new_users","loaded_at"))

    if staged_target is None:
        with staged_tables() as target:
            write_rows(*target)
    else:
        write_rows(*staged_target)
    if progress:
        progress("clickhouse")
    return {"campaigns": len(campaigns), "performance_rows": len(base_rows), "goal_rows": len(goal_rows),
            "criteria_rows": len(criteria_rows), "criteria_goal_rows": len(criteria_goal_rows),
            "visitor_rows": len(visitor_rows)}
