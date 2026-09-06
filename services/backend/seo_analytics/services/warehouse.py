from calendar import monthrange
from contextlib import nullcontext
from datetime import date, timedelta

from django.utils import timezone

from seo_analytics.models import SeoBrandMask, SeoGoal
from seo_analytics.services.clickhouse import (
    CONVERSION_TABLE,
    LANDING_TABLE,
    PHRASE_TABLE,
    TRAFFIC_TABLE,
    replace_month,
    staged_seo_tables,
)


ATTRIBUTION = "cross_device_last_significant"
ORGANIC_FILTER = "ym:s:<attribution>TrafficSource=='organic'"
METRICS = ["ym:s:visits", "ym:s:pageviews", "ym:s:users", "ym:s:newUsers"]


def month_bounds(month):
    return month, month.replace(day=monthrange(month.year, month.month)[1])


def iter_months(date_from, date_to):
    current = date_from.replace(day=1)
    last = date_to.replace(day=1)
    while current <= last:
        yield current
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)


def _dimension(row, index):
    dimensions = row.get("dimensions") or []
    item = dimensions[index] if index < len(dimensions) else {}
    return str((item or {}).get("name") or (item or {}).get("id") or "Не определено")


def _is_new_user(row, index):
    dimensions = row.get("dimensions") or []
    item = dimensions[index] if index < len(dimensions) else {}
    value = str((item or {}).get("id") or (item or {}).get("name") or "").strip().lower()
    return value in {"yes", "да", "true", "1"}


def _metrics(row, count):
    values = list(row.get("metrics") or []) + [0] * count
    return [max(0, int(round(float(value or 0)))) for value in values[:count]]


def _phrase_type(value, masks):
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    if normalized in {"", "не определено", "not defined", "undefined"}:
        return "Не определено"
    return "Брендовые" if any(mask in normalized for mask in masks) else "Небрендовые"


def _load_traffic(client, month, date1, date2, loaded_at, table=TRAFFIC_TABLE):
    payload = client.table_all(
        report_key=f"warehouse.traffic.{month:%Y-%m}",
        date1=date1, date2=date2,
        dimensions=[
            "ym:s:deviceCategory", "ym:s:<attribution>SearchEngineRoot", "ym:s:regionArea",
            "ym:s:isRobot", "ym:s:ageInterval", "ym:s:gender",
        ],
        metrics=METRICS, filters=ORGANIC_FILTER, attribution=ATTRIBUTION,
    )
    segmented_payload = client.table_all(
        report_key=f"warehouse.traffic-audience.{month:%Y-%m}",
        date1=date1, date2=date2,
        dimensions=[
            "ym:s:deviceCategory", "ym:s:<attribution>SearchEngineRoot", "ym:s:regionArea",
            "ym:s:isRobot", "ym:s:ageInterval", "ym:s:gender", "ym:s:isNewUser",
        ],
        metrics=["ym:s:visits", "ym:s:pageviews"],
        filters=ORGANIC_FILTER, attribution=ATTRIBUTION,
    )
    audience = {}
    for source in segmented_payload.get("data") or []:
        key = tuple(_dimension(source, index) for index in range(6))
        values = audience.setdefault(key, [0, 0, 0, 0])
        visits, pageviews = _metrics(source, 2)
        offset = 0 if _is_new_user(source, 6) else 2
        values[offset] += visits
        values[offset + 1] += pageviews
    rows = []
    for source in payload.get("data") or []:
        dimensions = tuple(_dimension(source, index) for index in range(6))
        rows.append((month, *dimensions, *_metrics(source, 4), *audience.get(dimensions, (0, 0, 0, 0)), loaded_at))
    replace_month(
        table, month, rows,
        ("month", "device", "search_engine", "region", "robotness",
         "age_interval", "gender", "visits", "pageviews", "users", "new_users",
         "new_visits", "new_pageviews", "returned_visits", "returned_pageviews", "loaded_at"),
    )
    return len(rows), payload.get("pages_loaded", 0) + segmented_payload.get("pages_loaded", 0)


def _load_phrases(client, month, date1, date2, loaded_at, masks, table=PHRASE_TABLE):
    payload = client.table_all(
        report_key=f"warehouse.phrases.{month:%Y-%m}",
        date1=date1, date2=date2,
        dimensions=["ym:s:<attribution>SearchEngineRoot", "ym:s:isRobot", "ym:s:<attribution>SearchPhrase"],
        metrics=METRICS,
        filters=ORGANIC_FILTER, attribution=ATTRIBUTION,
    )
    rows = []
    for source in payload.get("data") or []:
        phrase = _dimension(source, 2)
        rows.append((month, _dimension(source, 0), _dimension(source, 1), phrase,
                     _phrase_type(phrase, masks), *_metrics(source, 4), loaded_at))
    replace_month(
        table, month, rows,
        ("month", "search_engine", "robotness", "search_phrase", "phrase_type",
         "visits", "pageviews", "users", "new_users", "loaded_at"),
    )
    return len(rows), payload.get("pages_loaded", 0)


def _load_landings(client, month, date1, date2, loaded_at, table=LANDING_TABLE):
    payload = client.table_all(
        report_key=f"warehouse.landings.{month:%Y-%m}",
        date1=date1, date2=date2,
        dimensions=["ym:s:deviceCategory", "ym:s:<attribution>SearchEngineRoot", "ym:s:regionArea", "ym:s:startURL"],
        metrics=METRICS, filters=ORGANIC_FILTER, attribution=ATTRIBUTION,
    )
    rows = []
    for source in payload.get("data") or []:
        rows.append((month, *[_dimension(source, index) for index in range(4)], *_metrics(source, 4), loaded_at))
    replace_month(
        table, month, rows,
        ("month", "device", "search_engine", "region", "landing_url", "visits",
         "pageviews", "users", "new_users", "loaded_at"),
    )
    return len(rows), payload.get("pages_loaded", 0)


def _load_conversions(client, month, date1, date2, loaded_at, masks, goals, table=CONVERSION_TABLE, progress=None):
    rows = []
    pages = 0
    # Reporting API accepts at most 20 metrics; visits/users leave room for 9 goals.
    batches = [goals[index:index + 9] for index in range(0, len(goals), 9)] or [[]]
    for batch_index, batch in enumerate(batches, 1):
        metrics = ["ym:s:visits", "ym:s:users"]
        for goal in batch:
            metrics.extend((f"ym:s:goal{goal.external_id}reaches", f"ym:s:goal{goal.external_id}users"))
        payload = client.table_all(
            report_key=f"warehouse.conversions.{month:%Y-%m}.batch-{batch_index}",
            date1=date1, date2=date2,
            dimensions=["ym:s:deviceCategory", "ym:s:<attribution>SearchEngineRoot", "ym:s:regionArea", "ym:s:<attribution>SearchPhrase", "ym:s:ageInterval", "ym:s:gender"],
            metrics=metrics, filters=ORGANIC_FILTER, attribution=ATTRIBUTION,
        )
        pages += payload.get("pages_loaded", 0)
        for source in payload.get("data") or []:
            dimensions = [_dimension(source, index) for index in range(6)]
            phrase_type = _phrase_type(dimensions[3], masks)
            values = _metrics(source, len(metrics))
            if batch_index == 1:
                rows.append((month, *dimensions[:4], phrase_type, *dimensions[4:], 0, "Итого", 0, 0,
                             values[0], values[1], loaded_at))
            for goal_index, goal in enumerate(batch):
                metric_index = 2 + goal_index * 2
                rows.append((month, *dimensions[:4], phrase_type, *dimensions[4:], goal.external_id, goal.name,
                             values[metric_index], values[metric_index + 1], 0, 0, loaded_at))
        if progress:
            progress(batch_index, len(batches))
    replace_month(
        table, month, rows,
        ("month", "device", "search_engine", "region", "search_phrase", "phrase_type",
         "age_interval", "gender",
         "goal_id", "goal_name", "goal_reaches", "goal_users", "visits", "users", "loaded_at"),
    )
    return len(rows), pages


def refresh_warehouse(client, date_from, date_to, *, staged_target=None, progress=None):
    loaded_at = timezone.localtime()
    available_through = timezone.localdate() - timedelta(days=1)
    masks = [
        " ".join(value.strip().lower().replace("ё", "е").split())
        for value in SeoBrandMask.objects.filter(is_active=True).values_list("mask", flat=True)
    ]
    # The warehouse always contains every goal available in Metrika. The upload
    # file controls only which goals are shown and aggregated by the dashboard.
    goals = list(SeoGoal.objects.filter(is_available=True).order_by("position", "id"))
    stats = {}
    manager = staged_seo_tables() if staged_target is None else nullcontext(staged_target)
    with manager as tables:
        for month in iter_months(date_from, date_to):
            month_start, month_end = month_bounds(month)
            effective_start = month_start.isoformat()
            effective_end = min(month_end, available_through).isoformat()
            month_stats = {}
            month_stats["traffic"] = _load_traffic(
                client, month, effective_start, effective_end, loaded_at, tables[TRAFFIC_TABLE]
            )
            if progress:
                progress(month, "traffic")
            month_stats["phrases"] = _load_phrases(
                client, month, effective_start, effective_end, loaded_at, masks, tables[PHRASE_TABLE]
            )
            if progress:
                progress(month, "phrases")
            month_stats["conversions"] = _load_conversions(
                client, month, effective_start, effective_end, loaded_at, masks, goals,
                tables[CONVERSION_TABLE],
                progress=(lambda batch, total: progress(month, f"conversions:{batch}/{total}")) if progress else None,
            )
            month_stats["landings"] = _load_landings(
                client, month, effective_start, effective_end, loaded_at, tables[LANDING_TABLE]
            )
            if progress:
                progress(month, "landings")
            stats[month.isoformat()] = month_stats
            if progress:
                progress(month, "complete", month_stats)
    return stats
