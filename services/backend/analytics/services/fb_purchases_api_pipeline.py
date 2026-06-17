import logging
from datetime import date

from datasets.services.external_api.fb_purchases_api_loader import (
    load_fb_purchases_raw_from_api,
)
from analytics.services.fb_purchases_rebuild_sql import (
    rebuild_fb_purchases_use_from_raw_sql,
)
from analytics.services.fb_purchases_sync import sync_fb_purchases_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.fb_purchases")


def run_fb_purchases_api_pipeline(
    start_date: date | None = None,
    end_date: date | None = None,
):
    logger.info("FBPurchases pipeline started")

    try:
        raw_result = load_fb_purchases_raw_from_api(
            start_date=start_date,
            end_date=end_date,
        )

        rebuild_result = rebuild_fb_purchases_use_from_raw_sql()

        clickhouse_result = sync_fb_purchases_to_clickhouse()

        invalidate_dashboard_by_name("Purchases")
        notify_dashboard_updated("Purchases")

        result = {
            "status": "ok",
            "source": "api",
            "dashboard": "Purchases",
            "raw": raw_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
        }

        logger.info("FBPurchases pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("FBPurchases pipeline failed")

        send_bitrix_message(
            f"[b]fb_purchases API[/b]\n"
            f"Ошибка загрузки Purchases:\n{exc}",
            logger_name="external_api.fb_purchases",
        )

        raise