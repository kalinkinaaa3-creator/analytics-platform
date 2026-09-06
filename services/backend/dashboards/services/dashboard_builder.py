from datetime import date, timedelta
from copy import deepcopy
from django.core.cache import cache

from analytics.clickhouse.repository import ClickHouseRepository

from dashboards.models import Dashboard, DashboardAccess
from dashboards.cache.dashboard_cache import dashboard_cache_key
from dashboards.services.tables import build_table
from dashboards.services.charts import build_line_chart

import hashlib
import json
from analytics.services.fb_project_prepare import prepare_fb_project_gantt
from analytics.services.yd_wordstat_prepare import prepare_yd_wordstat_table
from analytics.services.fb_purchases_prepare import prepare_fb_purchases_dashboard
from analytics.services.fb_turnover_prepare import prepare_fb_turnover_dashboard
from analytics.services.fb_accreceiv_prepare import prepare_fb_accreceiv_dashboard

from analytics.services.planned_sales_prepare import prepare_planned_sales_dashboard

from analytics.services.revenue_sales_prepare import prepare_revenue_dashboard


from rest_framework.exceptions import PermissionDenied
from dashboards.services.access import user_can_view_dashboard






def get_dashboard_cache_timeout(dashboard: Dashboard) -> int:
    timeouts = {
        "Projects": 24 * 3600,    # 24 часа
        "Wordstat": 24 * 3600,    # 24 часа
        "Purchases": 24 * 3600,   # 24 часа
        "Turnover": 24 * 3600,    # 24 часа
        "Accreceiv": 24 * 3600,   # 24 часа
        "PlannedSales": 24 * 3600,
        "Revenue": 24 * 3600,
    }

    return timeouts.get(dashboard.name, 300)


def get_dashboard_cache_schema_version(dashboard: Dashboard) -> int:
    return {
        "Wordstat": 4,
        "Turnover": 3,
    }.get(dashboard.name, 1)



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
            "metadata_only",
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
            "tree_month",
        ]

    elif dashboard.name == "Accreceiv":
        keys = [
            "partner",
            "contract_partner",
            "manager_name",
            "date_start",
            "date_end",
        ]

    elif dashboard.name == "PlannedSales":
        keys = [
            "date",
        ]

    elif dashboard.name == "Revenue":
        keys = [
            "direction",
            "project",
            "manager",
            "partner",
            "consignee",
            "nom_view",
            "nom_category",
            "nom_group",
            "nom",
            "nom_code",
            "nom_hier",
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

        if isinstance(value, tuple):
            value = list(value)

        if isinstance(value, list):
            value = [
                item
                for item in value
                if item not in ("", None)
            ]

            value = sorted(
                value,
                key=lambda item: str(item),
            )

        normalized[key] = value

    return normalized



def apply_default_filters_for_dashboard(dashboard: Dashboard, filters: dict) -> dict:
    result = dict(filters)

    today = date.today()
    yesterday = today - timedelta(days=1)

    if dashboard.name == "Projects":
        if not result.get("project_start"):
            result["project_start"] = f"{today.year - 1}-01-01"

        if not result.get("project_end"):
            result["project_end"] = f"{today.year + 1}-12-31"

    elif dashboard.name == "Purchases":
        if not result.get("date_start"):
            result["date_start"] = f"{yesterday.year}-01-01"

        if not result.get("date_end"):
            result["date_end"] = yesterday.isoformat()

    elif dashboard.name in ("Turnover", "Accreceiv"):
        if not result.get("date_start"):
            result["date_start"] = f"{yesterday.year}-01-01"

        if not result.get("date_end"):
            result["date_end"] = yesterday.isoformat()

    elif dashboard.name == "Revenue":
        if not result.get("date_start"):
            result["date_start"] = f"{today.year}-01-01"

        if not result.get("date_end"):
            result["date_end"] = today.isoformat()

    return result




def clean_runtime_filters(filters: dict | None = None) -> dict:
    filters = filters or {}

    return {
        key: value
        for key, value in filters.items()
        if value not in ("", None, [], ())
    }


def _can_edit_dashboard(user, dashboard) -> bool:
    if user is None:
        return False
    if user.is_superuser or dashboard.owner_id == user.id:
        return True
    return DashboardAccess.objects.filter(
        user=user,
        dashboard=dashboard,
        can_edit=True,
    ).exists()





def build_dashboard(dashboard_id: int, user=None, filters: dict | None = None):

    queryset = Dashboard.objects.prefetch_related("widgets")

    dashboard = queryset.get(id=dashboard_id)

    if user is not None and not user_can_view_dashboard(user, dashboard):
        raise PermissionDenied("Нет доступа к этому дашборду")

    cache_filters = normalize_filters_for_dashboard(
        dashboard=dashboard,
        filters=filters,
    )

    cache_filters = apply_default_filters_for_dashboard(
        dashboard=dashboard,
        filters=cache_filters,
    )

    runtime_filters = clean_runtime_filters(cache_filters)

    cache_schema_version = get_dashboard_cache_schema_version(dashboard)
    cache_key_payload = cache_filters
    if cache_schema_version > 1:
        cache_key_payload = {
            "schema_version": cache_schema_version,
            "filters": cache_filters,
        }
    if dashboard.name == "Wordstat":
        cache_key_payload["generation"] = cache.get("wordstat:statistics:generation", "initial")
    filters_hash = hashlib.md5(
        json.dumps(cache_key_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    shared_key = dashboard_cache_key(
        f"dashboard:{dashboard_id}:filters:{filters_hash}"
    )

    if user is not None:
        key = dashboard_cache_key(
            f"user:{user.id}:dashboard:{dashboard_id}:filters:{filters_hash}"
        )
    else:
        key = shared_key

    cached = cache.get(key)
    
    if cached is not None:
        return cached

    if user is not None:
        shared_result = cache.get(shared_key)
        if shared_result is not None:
            result = deepcopy(shared_result)
            result["dashboard"]["can_edit"] = _can_edit_dashboard(user, dashboard)
            cache.set(key, result, timeout=get_dashboard_cache_timeout(dashboard))
            return result

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
        wordstat_metadata = widget.type == "yd_wordstat_table" and str(runtime_filters.get("metadata_only", "")).lower() in ("1", "true")

        if dataset_id and not wordstat_metadata:
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
            project_filters = dict(runtime_filters)

            today = date.today()

            if not project_filters.get("project_start"):
                project_filters["project_start"] = f"{today.year - 1}-01-01"

            if not project_filters.get("project_end"):
                project_filters["project_end"] = f"{today.year + 1}-12-31"

            rows = repository.fetch_fb_project_rows()

            widget_data["data"] = prepare_fb_project_gantt(
                rows=rows,
                filters=project_filters,
            )

        elif wordstat_metadata:
            widget_data["data"] = {"revision": cache_key_payload.get("generation", "initial"), "filters": {key: runtime_filters.get(key, []) for key in ("feature", "category", "phrase")}}

        elif widget.type == "yd_wordstat_table":
            page = int(runtime_filters.get("page", 1))
            page_size = int(runtime_filters.get("page_size", 100))
            page = max(1, page)
            page_size = min(max(1, page_size), 500)
            offset = (page - 1) * page_size

            rows = repository.fetch_yd_wordstat_rows(
                filters=runtime_filters,
                limit=page_size,
                offset=offset,
            )
            wordstat_base_filters = {
                key: value
                for key, value in runtime_filters.items()
                if key not in ("page", "page_size")
            }
            wordstat_base_filters["generation"] = cache_key_payload.get("generation", "initial")
            wordstat_base_hash = hashlib.md5(
                json.dumps(wordstat_base_filters, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            wordstat_base_key = dashboard_cache_key(
                f"dashboard:{dashboard_id}:filters:wordstat-base:{wordstat_base_hash}"
            )
            wordstat_base = cache.get(wordstat_base_key)
            if wordstat_base is None:
                wordstat_base = {
                    "total_rows": repository.fetch_yd_wordstat_count(filters=runtime_filters),
                    "summary_source_rows": repository.fetch_yd_wordstat_summary_rows(filters=runtime_filters),
                    "filter_options": repository.fetch_yd_wordstat_filter_options(filters=runtime_filters),
                }
                cache.set(
                    wordstat_base_key,
                    wordstat_base,
                    timeout=get_dashboard_cache_timeout(dashboard),
                )

            total_rows = wordstat_base["total_rows"]
            page_phrases = sorted({row.get("phrase") for row in rows if row.get("phrase")})
            context_filters = dict(runtime_filters)
            context_filters["phrase"] = page_phrases
            context_rows = repository.fetch_yd_wordstat_rows(filters=context_filters) if page_phrases else []
            summary_source_rows = wordstat_base["summary_source_rows"]
            filter_options = wordstat_base["filter_options"]

            widget_data["data"] = prepare_yd_wordstat_table(
                rows=rows,
                filters=runtime_filters,
                filter_options=filter_options,
                context_rows=context_rows,
                summary_source_rows=summary_source_rows,
                total_rows=total_rows,
                page=page,
                page_size=page_size,
            )

        elif widget.type == "fb_purchases_dashboard":
            purchases_filters = dict(runtime_filters)

            today = date.today()

            if not purchases_filters.get("date_start"):
                purchases_filters["date_start"] = f"{today.year}-01-01"

            if not purchases_filters.get("date_end"):
                purchases_filters["date_end"] = today.isoformat()

            rows = repository.fetch_fb_purchases_use_rows(filters=purchases_filters)
            indicator_rows = repository.fetch_fb_purchases_indicator_rows(filters=purchases_filters)
            filter_options = repository.fetch_fb_purchases_filter_options(filters=purchases_filters)

            widget_data["data"] = prepare_fb_purchases_dashboard(
                rows=rows,
                indicator_rows=indicator_rows,
                filters=purchases_filters,
                filter_options=filter_options,
            )

        elif widget.type == "fb_turnover_dashboard":
            turnover_filters = dict(runtime_filters)
            tree_month = turnover_filters.get("tree_month")

            yesterday = date.today() - timedelta(days=1)

            if not turnover_filters.get("date_start"):
                turnover_filters["date_start"] = f"{yesterday.year}-01-01"

            if not turnover_filters.get("date_end"):
                turnover_filters["date_end"] = yesterday.isoformat()

            rows = repository.fetch_fb_turnover_use_rows(filters=turnover_filters)

            if tree_month:
                widget_data["data"] = prepare_fb_turnover_dashboard(
                    rows=rows,
                    indicator_rows=[],
                    filters=turnover_filters,
                    tree_only=True,
                )
                widgets_data.append(widget_data)
                continue

            indicator_rows = repository.fetch_fb_turnover_indicator_rows(filters=turnover_filters)
            filter_options = repository.fetch_fb_turnover_filter_options(filters=turnover_filters)

            widget_data["data"] = prepare_fb_turnover_dashboard(
                rows=rows,
                indicator_rows=indicator_rows,
                filters=turnover_filters,
                filter_options=filter_options,
            )

        elif widget.type == "fb_accreceiv_dashboard":
            accreceiv_filters = dict(runtime_filters)

            yesterday = date.today() - timedelta(days=1)

            if not accreceiv_filters.get("date_start"):
                accreceiv_filters["date_start"] = f"{yesterday.year}-01-01"

            if not accreceiv_filters.get("date_end"):
                accreceiv_filters["date_end"] = yesterday.isoformat()

            rows = repository.fetch_fb_accreceiv_use_rows(filters=accreceiv_filters)
            indicator_rows = repository.fetch_fb_accreceiv_indicator_rows(filters=accreceiv_filters)
            filter_options = repository.fetch_fb_accreceiv_filter_options(filters=accreceiv_filters)

            widget_data["data"] = prepare_fb_accreceiv_dashboard(
                rows=rows,
                indicator_rows=indicator_rows,
                filters=accreceiv_filters,
                filter_options=filter_options,
            )

        elif widget.type == "planned_sales_dashboard":
            selected_date = runtime_filters.get("date")

            if not selected_date:
                selected_date = date.today().replace(day=1).strftime("%Y-%m-01")

            if selected_date:
                date_start = f"{selected_date[:4]}-01-01"
                date_end = selected_date
            else:
                date_start = None
                date_end = None

            planned_sales_filters = {}

            if date_start:
                planned_sales_filters["date_start"] = date_start

            if date_end:
                planned_sales_filters["date_end"] = date_end

            rows = repository.fetch_planned_sales_rows(
                filters=planned_sales_filters,
            )

            available_dates = repository.fetch_planned_sales_dates()

            # Получаем дату последнего обновления
            last_update = repository.fetch_planned_sales_last_update()

            widget_data["data"] = prepare_planned_sales_dashboard(
                rows=rows,
                filters={
                    "date": selected_date or "",
                    "date_start": date_start or "",
                    "date_end": date_end or "",
                },
                available_dates=available_dates,
                last_update=last_update,
            )

        elif widget.type == "revenue_dashboard":
            revenue_filters = dict(runtime_filters)

            rows = repository.fetch_revenue_sales_rows(
                filters=revenue_filters,
            )

            filter_options = repository.fetch_revenue_sales_filter_options(
                filters=revenue_filters,
            )

            last_update = repository.fetch_revenue_sales_last_update()

            widget_data["data"] = prepare_revenue_dashboard(
                rows=rows,
                filters=revenue_filters,
                filter_options=filter_options,
                last_update=last_update,
            )

        elif widget.type == "crm_analytics_dashboard":
            # The dedicated CRM component loads compact aggregate and paginated
            # endpoints. Do not duplicate that payload in the generic builder.
            widget_data["data"] = {}

        elif widget.type == "seo_analytics_dashboard":
            # SEO pages load independent cached blocks through their own API.
            widget_data["data"] = {}
        elif widget.type == "context_analytics_dashboard":
            widget_data["data"] = {}
        elif widget.type == "lead_generation_dashboard":
            widget_data["data"] = {}




        widgets_data.append(widget_data)

    can_edit = _can_edit_dashboard(user, dashboard)

    result = {
        "dashboard": {
            "id": dashboard.id,
            "name": dashboard.name,
            "owner": dashboard.owner_id,
            "can_edit": can_edit,
        },
        "widgets": widgets_data,
    }

    cache_timeout = get_dashboard_cache_timeout(dashboard)
    cache.set(key, result, timeout=cache_timeout)
    if user is not None:
        shared_result = deepcopy(result)
        shared_result["dashboard"]["can_edit"] = False
        cache.set(shared_key, shared_result, timeout=cache_timeout)

    return result
