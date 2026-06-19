import logging
from datetime import date

from datasets.services.external_api.planned_sales_csv_loader import (
    load_dash_sales_from_csv,
)
from analytics.services.planned_sales_rebuild_sql import (
    rebuild_planned_sales_from_dash_sales_sql,
)
from analytics.services.planned_sales_sync import (
    sync_planned_sales_to_clickhouse,
)
from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.planned_sales")


def run_planned_sales_csv_pipeline(
    csv_path: str,
    start_date: date | None = None,
    truncate_source: bool = True,
):
    logger.info("PlannedSales CSV pipeline started")

    csv_result = load_dash_sales_from_csv(
        csv_path=csv_path,
        start_date=start_date,
        truncate=truncate_source,
    )

    logger.info("PlannedSales SQL rebuild started")
    rebuild_result = rebuild_planned_sales_from_dash_sales_sql()

    logger.info("PlannedSales ClickHouse sync started")
    clickhouse_result = sync_planned_sales_to_clickhouse()

    logger.info("PlannedSales ClickHouse sync finished: %s", clickhouse_result)

    invalidate_dashboard_by_name("PlannedSales")
    logger.info("PlannedSales dashboard cache invalidated")

    notify_dashboard_updated("PlannedSales")
    logger.info("PlannedSales websocket notification sent")

    result = {
        "status": "ok",
        "source": "csv",
        "dashboard": "PlannedSales",
        "dash_sales": csv_result,
        "rebuild": rebuild_result,
        "clickhouse": clickhouse_result,
    }

    logger.info("PlannedSales CSV pipeline finished: %s", result)

    return result