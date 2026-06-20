import logging

from datasets.services.external_api.fb_accreceiv_csv_loader import (
    load_accreceiv_raw_from_csv,
)
from analytics.services.fb_accreceiv_rebuild_sql import (
    rebuild_fb_accreceiv_use_from_raw_sql,
)
from analytics.services.fb_accreceiv_sync import sync_fb_accreceiv_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.fb_accreceiv")


def run_fb_accreceiv_csv_pipeline(
    csv_path: str,
    truncate_source: bool = True,
):
    logger.info("FBAccreceiv CSV pipeline started")

    try:
        raw_result = load_accreceiv_raw_from_csv(
            csv_path=csv_path,
            truncate_source=truncate_source,
        )

        rebuild_result = rebuild_fb_accreceiv_use_from_raw_sql()

        clickhouse_result = sync_fb_accreceiv_to_clickhouse()

        invalidate_dashboard_by_name("Accreceiv")
        logger.info("FBAccreceiv dashboard cache invalidated")

        notify_dashboard_updated("Accreceiv")
        logger.info("FBAccreceiv websocket notification sent")

        result = {
            "status": "ok",
            "source": "csv",
            "dashboard": "Accreceiv",
            "raw": raw_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
        }

        logger.info("FBAccreceiv CSV pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("FBAccreceiv CSV pipeline failed")

        send_bitrix_message(
            f"[b]fb_accreceiv CSV[/b]\n"
            f"Ошибка загрузки Accreceiv из CSV:\n{exc}",
            logger_name="external_api.fb_accreceiv",
        )

        raise



'''
from analytics.services.fb_accreceiv_csv_pipeline import run_fb_accreceiv_csv_pipeline

run_fb_accreceiv_csv_pipeline(
    csv_path="/app/media/datasets/fb_accreceiv.csv",
    truncate_source=True,
)
'''