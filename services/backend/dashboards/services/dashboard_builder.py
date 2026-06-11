from django.core.cache import cache

from analytics.clickhouse.repository import ClickHouseRepository

from dashboards.models import Dashboard
from dashboards.cache.dashboard_cache import dashboard_cache_key
from dashboards.services.tables import build_table
from dashboards.services.charts import build_line_chart

import hashlib
import json
from analytics.services.fb_project_prepare import prepare_fb_project_gantt


def build_dashboard(dashboard_id: int, user=None, filters: dict | None = None):


    filters = filters or {}

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
    if cached:
        return cached

    queryset = Dashboard.objects.prefetch_related("widgets")

    if user is not None:
        queryset = queryset.filter(owner=user)

    dashboard = queryset.get(id=dashboard_id)

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

        widgets_data.append(widget_data)

    result = {
        "dashboard": {
            "id": dashboard.id,
            "name": dashboard.name,
            "owner": dashboard.owner_id,
        },
        "widgets": widgets_data,
    }

    cache.set(key, result, timeout=300)

    return result