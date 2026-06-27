import logging

from datasets.services.external_api.yd_wordstat_all_csv_loader import (
    load_yd_wordstat_all_raw_from_csv,
)
from datasets.services.external_api.yd_wordstat_device_csv_loader import (
    load_yd_wordstat_device_raw_from_csv,
)
from datasets.services.external_api.yd_wordstat_region_csv_loader import (
    load_yd_wordstat_region_raw_from_csv,
)

from analytics.services.yd_wordstat_rebuild_sql import (
    rebuild_yd_wordstat_for_from_raw_sql,
)
from analytics.services.yd_wordstat_sync import sync_yd_wordstat_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.yd_wordstat")


def run_yd_wordstat_csv_pipeline(
    source: str,
    csv_path: str,
    truncate_source: bool = True,
):
    logger.info(
        "YD Wordstat CSV pipeline started: source=%s, csv_path=%s",
        source,
        csv_path,
    )

    try:
        if source == "all":
            raw_result = load_yd_wordstat_all_raw_from_csv(
                csv_path=csv_path,
                truncate_source=truncate_source,
            )
        elif source == "device":
            raw_result = load_yd_wordstat_device_raw_from_csv(
                csv_path=csv_path,
                truncate_source=truncate_source,
            )
        elif source == "region":
            raw_result = load_yd_wordstat_region_raw_from_csv(
                csv_path=csv_path,
                truncate_source=truncate_source,
            )
        else:
            raise ValueError(
                "source must be one of: all, device, region"
            )

        rebuild_result = rebuild_yd_wordstat_for_from_raw_sql()

        clickhouse_result = sync_yd_wordstat_to_clickhouse()

        invalidate_dashboard_by_name("Wordstat")
        notify_dashboard_updated("Wordstat")

        result = {
            "status": "ok",
            "source": "csv",
            "raw_source": source,
            "raw": raw_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
        }

        logger.info("YD Wordstat CSV pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("YD Wordstat CSV pipeline failed")

        send_bitrix_message(
            f"[b]yd_wordstat CSV[/b]\n"
            f"Ошибка CSV-загрузки Wordstat.\n"
            f"Источник: {source}\n"
            f"Ошибка: {exc}",
            logger_name="external_api.yd_wordstat",
        )

        raise