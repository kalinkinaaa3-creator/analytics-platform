import logging
from datetime import date

from datasets.services.external_api.fb_project_api_loader import load_fb_project_from_api
from analytics.services.fb_project_sync import sync_fb_project_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.fb_project")


def run_fb_project_api_pipeline(load_date: date | None = None):
    logger.info("FBProject pipeline started")

    try:
        postgres_result = load_fb_project_from_api(load_date=load_date)

        logger.info("FBProject ClickHouse sync started")
        clickhouse_result = sync_fb_project_to_clickhouse()
        logger.info("FBProject ClickHouse sync finished: %s", clickhouse_result)

        invalidate_dashboard_by_name("Projects")
        logger.info("FBProject dashboard cache invalidated")

        notify_dashboard_updated("Projects")
        logger.info("FBProject websocket notification sent")

        result = {
            "status": "ok",
            "source": "api",
            "postgres": postgres_result,
            "clickhouse": clickhouse_result,
            "dashboard": "Projects",
        }

        logger.info("FBProject pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("FBProject pipeline failed")

        send_bitrix_message(
            f"[b]fb_project API[/b]\n"
            f"Ошибка загрузки Projects:\n{exc}",
            logger_name="external_api.fb_project",
        )

        raise