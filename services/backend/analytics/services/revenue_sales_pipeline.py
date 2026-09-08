import logging

from analytics.services.revenue_sales_rebuild_sql import (
    rebuild_revenue_sales_from_dash_sales_sql,
)
from analytics.services.revenue_sales_sync import sync_revenue_sales_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("analytics.revenue_sales")


def run_revenue_sales_pipeline():
    logger.info("RevenueSales pipeline started")

    try:
        rebuild_result = rebuild_revenue_sales_from_dash_sales_sql()

        logger.info("RevenueSales ClickHouse sync started")

        clickhouse_result = sync_revenue_sales_to_clickhouse()

        logger.info("RevenueSales ClickHouse sync finished: %s", clickhouse_result)

        invalidate_dashboard_by_name("Revenue")
        logger.info("Revenue dashboard cache invalidated")

        notify_dashboard_updated("Revenue")
        logger.info("Revenue websocket notification sent")

        from lead_generation.cache import invalidate_lead_generation_cache
        invalidate_lead_generation_cache()
        invalidate_dashboard_by_name("LeadGeneration")
        notify_dashboard_updated("LeadGeneration")

        result = {
            "status": "ok",
            "dashboard": "Revenue",
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
        }

        logger.info("RevenueSales pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("RevenueSales pipeline failed")

        send_bitrix_message(
            f"[b]RevenueSales[/b]\n"
            f"Ошибка пересборки дашборда выручки:\n{exc}",
            logger_name="analytics.revenue_sales",
        )

        raise