from django.core.cache import cache

from analytics.clickhouse.repository import ClickHouseRepository

from dashboards.models import Dashboard
from dashboards.cache.dashboard_cache import dashboard_cache_key
from dashboards.services.tables import build_table
from dashboards.services.charts import build_line_chart

import hashlib
import json
from analytics.services.fb_project_prepare import prepare_fb_project_gantt
from analytics.services.yd_wordstat_prepare import prepare_yd_wordstat_table
from analytics.services.fb_purchases_prepare import prepare_fb_purchases_dashboard
from analytics.services.fb_turnover_prepare import prepare_fb_turnover_dashboard




def get_dashboard_cache_timeout(dashboard: Dashboard) -> int:
    timeouts = {
        "Projects": 24 * 3600,    # 24 часа
        "Wordstat": 24 * 3600,    # 24 часа
        "Purchases": 24 * 3600,   # 24 часа
        "Turnover": 24 * 3600,    # 24 часа
    }

    return timeouts.get(dashboard.name, 300)



def normalize_filters_for_dashboard(dashboard: Dashboard, filters: dict | None = None) -> dict:
    filters = filters or {}

    if dashboard.name == "Projects":
        keys = [
            "project_name",
            "project_type",
            "department",
            "deviation_project",
            "project_manager",
            "project_status",
            "folder_lvl1",
            "folder_lvl2",
            "folder_lvl3",
            "project_start",
            "project_end",
        ]

    elif dashboard.name == "Wordstat":
        keys = [
            "feature",
            "category",
            "phrase",
            "page",
            "page_size",
        ]

    elif dashboard.name == "Purchases":
        keys = [
            "nomenclature_code",
            "nomenclature",
            "partner",
            "date_start",
            "date_end",
        ]

    elif dashboard.name == "Turnover":
        keys = [
            "nomenclature",
            "warehouse_group",
            "warehouse",
            "quantity",
            "date_start",
            "date_end",
        ]

    else:
        keys = sorted(filters.keys())

    normalized = {}

    for key in keys:
        value = filters.get(key, "")

        if value is None:
            value = ""

        normalized[key] = value

    return normalized







def build_dashboard(dashboard_id: int, user=None, filters: dict | None = None):

    queryset = Dashboard.objects.prefetch_related("widgets")

    if user is not None:
        queryset = queryset.filter(owner=user)

    dashboard = queryset.get(id=dashboard_id)

    filters = normalize_filters_for_dashboard(
        dashboard=dashboard,
        filters=filters,
    )

    filters_hash = hashlib.md5(
        json.dumps(filters, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    if user is not None:
        key = dashboard_cache_key(
            f"user:{user.id}:dashboard:{dashboard_id}:filters:{filters_hash}"
        )
    else:
        key = dashboard_cache_key(
            f"dashboard:{dashboard_id}:filters:{filters_hash}"
        )

    cached = cache.get(key)
    
    if cached is not None:
        return cached

    repository = ClickHouseRepository()

    widgets_data = []

    for widget in dashboard.widgets.all().order_by("position"):

        config = widget.config or {}

        widget_data = {
            "id": widget.id,
            "type": widget.type,
            "position": widget.position,
            "config": config,
            "data": None,
        }

        dataset_id = config.get("dataset_id")

        if dataset_id:
            rows = repository.fetch_dataset_rows(dataset_id)
        else:
            rows = []

        if widget.type == "table":
            widget_data["data"] = build_table(rows)

        elif widget.type == "line_chart":
            widget_data["data"] = build_line_chart(
                rows,
                config.get("x", "id"),
                config.get("y", "amount"),
            )

        elif widget.type == "fb_project_gantt":
            rows = repository.fetch_fb_project_rows(
                filters=filters,
            )

            widget_data["data"] = prepare_fb_project_gantt(
                rows=rows,
                filters=filters,
            )

        elif widget.type == "yd_wordstat_table":
            page = int(filters.get("page", 1))
            page_size = int(filters.get("page_size", 100))

            rows = repository.fetch_yd_wordstat_rows(
                filters=filters,
            )

            widget_data["data"] = prepare_yd_wordstat_table(
                rows=rows,
                filters=filters,
                page=page,
                page_size=page_size,
            )

        elif widget.type == "fb_purchases_dashboard":
            rows = repository.fetch_fb_purchases_use_rows(filters=filters)
            indicator_rows = repository.fetch_fb_purchases_indicator_rows(filters=filters)

            widget_data["data"] = prepare_fb_purchases_dashboard(
                rows=rows,
                indicator_rows=indicator_rows,
                filters=filters,
            )

        elif widget.type == "fb_turnover_dashboard":
            rows = repository.fetch_fb_turnover_use_rows(filters=filters)
            indicator_rows = repository.fetch_fb_turnover_indicator_rows(filters=filters)

            widget_data["data"] = prepare_fb_turnover_dashboard(
                rows=rows,
                indicator_rows=indicator_rows,
                filters=filters,
            )




        widgets_data.append(widget_data)

    result = {
        "dashboard": {
            "id": dashboard.id,
            "name": dashboard.name,
            "owner": dashboard.owner_id,
        },
        "widgets": widgets_data,
    }

    cache_timeout = get_dashboard_cache_timeout(dashboard)
    cache.set(key, result, timeout=cache_timeout)

    return result