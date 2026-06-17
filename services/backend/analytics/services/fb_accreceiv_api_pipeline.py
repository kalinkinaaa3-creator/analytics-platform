import logging
from datetime import date

from datasets.services.external_api.fb_accreceiv_api_loader import (
    load_accreceiv_raw_from_api,
)
from analytics.services.fb_accreceiv_rebuild_sql import (
    rebuild_fb_accreceiv_use_from_raw_sql,
)
from analytics.services.fb_accreceiv_sync import sync_fb_accreceiv_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.fb_accreceiv")


def run_fb_accreceiv_api_pipeline(
    start_date: date | None = None,
    end_date: date | None = None,
):
    logger.info("FBAccreceiv pipeline started")

    try:
        raw_result = load_accreceiv_raw_from_api(
            start_date=start_date,
            end_date=end_date,
        )

        rebuild_result = rebuild_fb_accreceiv_use_from_raw_sql()

        clickhouse_result = sync_fb_accreceiv_to_clickhouse()

        invalidate_dashboard_by_name("Accreceiv")
        logger.info("FBAccreceiv dashboard cache invalidated")

        notify_dashboard_updated("Accreceiv")
        logger.info("FBAccreceiv websocket notification sent")

        result = {
            "status": "ok",
            "source": "api",
            "dashboard": "Accreceiv",
            "raw": raw_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
        }

        logger.info("FBAccreceiv pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("FBAccreceiv pipeline failed")

        send_bitrix_message(
            f"[b]fb_accreceiv API[/b]\n"
            f"Ошибка загрузки Accreceiv:\n{exc}",
            logger_name="external_api.fb_accreceiv",
        )

        raise