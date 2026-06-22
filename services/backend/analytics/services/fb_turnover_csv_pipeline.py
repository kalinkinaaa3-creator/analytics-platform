import logging

from django.core.management import call_command

from datasets.services.external_api.fb_turnover_csv_loader import (
    load_turnover_raw_from_csv,
)
from analytics.services.fb_turnover_rebuild_sql import (
    rebuild_fb_turnover_use_from_raw_sql,
)
from analytics.services.fb_turnover_sync import sync_fb_turnover_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.fb_turnover")


def run_fb_turnover_csv_pipeline(
    csv_path: str,
    truncate_source: bool = True,
):
    logger.info("FBTurnover CSV pipeline started")

    try:
        raw_result = load_turnover_raw_from_csv(
            csv_path=csv_path,
            truncate_source=truncate_source,
        )

        rebuild_result = rebuild_fb_turnover_use_from_raw_sql()

        clickhouse_result = sync_fb_turnover_to_clickhouse()

        invalidate_dashboard_by_name("Turnover")
        logger.info("FBTurnover dashboard cache invalidated")

        call_command("warmup_turnover_cache")
        logger.info("FBTurnover cache warmup finished")

        notify_dashboard_updated("Turnover")
        logger.info("FBTurnover websocket notification sent")

        result = {
            "status": "ok",
            "source": "csv",
            "dashboard": "Turnover",
            "raw": raw_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
            "cache": {
                "invalidated": "Turnover",
                "warmed": True,
                "command": "warmup_turnover_cache",
            },
        }

        logger.info("FBTurnover CSV pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("FBTurnover CSV pipeline failed")

        send_bitrix_message(
            f"[b]fb_turnover CSV[/b]\n"
            f"Ошибка загрузки Turnover из CSV:\n{exc}",
            logger_name="external_api.fb_turnover",
        )

        raise



'''
from analytics.services.fb_turnover_csv_pipeline import run_fb_turnover_csv_pipeline

run_fb_turnover_csv_pipeline(
    csv_path="/app/media/datasets/fb_turnover.csv",
    truncate_source=True,
)
'''