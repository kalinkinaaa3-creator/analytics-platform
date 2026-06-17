import logging
from datetime import date

from datasets.services.external_api.planned_sales_api_loader import load_dash_sales_from_api
from analytics.services.planned_sales_rebuild_sql import rebuild_planned_sales_from_dash_sales_sql
from analytics.services.planned_sales_sync import sync_planned_sales_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.planned_sales")


def run_planned_sales_api_pipeline(
    start_date: date | None = None,
    end_date: date | None = None,
):
    logger.info("PlannedSales pipeline started")

    try:
        dash_sales_result = load_dash_sales_from_api(
            start_date=start_date,
            end_date=end_date,
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
            "source": "api",
            "dashboard": "PlannedSales",
            "dash_sales": dash_sales_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
        }

        logger.info("PlannedSales pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("PlannedSales pipeline failed")

        send_bitrix_message(
            f"[b]planned_sales API[/b]\n"
            f"Ошибка загрузки PlannedSales:\n{exc}",
            logger_name="external_api.planned_sales",
        )

        raise