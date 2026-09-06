import logging
from contextlib import contextmanager

from django.conf import settings
from django.db import connection
from django.utils import timezone

from datasets.services.external_api.yd_wordstat_api_loader import (
    check_regions, get_configuration, make_jobs, load_job, validate_download,
)

logger = logging.getLogger("external_api.yd_wordstat")
LOCK_ID = 815734020


@contextmanager
def wordstat_pipeline_lock():
    """Keep concurrent full/manual runs from replacing the same data."""
    if connection.vendor != "postgresql":
        raise RuntimeError("Wordstat loading requires PostgreSQL advisory locks")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        if not cursor.fetchone()[0]:
            raise RuntimeError("Another Wordstat API load is already running")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])


def _notify(message):
    try:
        from analytics.services.bitrix_notify import send_bitrix_message
        send_bitrix_message(message, logger_name="external_api.yd_wordstat")
    except Exception:
        logger.exception("Wordstat notification failed")


def notify_wordstat_updated():
    """A socket outage must not stop publication of the remaining mart."""
    try:
        from dashboards.realtime import notify_dashboard_updated
        notify_dashboard_updated("Wordstat")
    except Exception:
        logger.exception("Wordstat was published, but its WebSocket notification failed")


def _run_pipeline(source=None):
    if not settings.YD_WORDSTAT_V2_LOAD_ENABLED:
        raise RuntimeError("Wordstat v2 loading is disabled. Run the plan and probe before enabling YD_WORDSTAT_V2_LOAD_ENABLED.")
    if source not in (None, "all", "device", "region"):
        raise ValueError("source must be all, device or region (IPLAST aggregates)")
    # Fix the target month even when a long run crosses a calendar boundary.
    today = timezone.localdate()
    with wordstat_pipeline_lock():
        config = get_configuration()
        region_check = check_regions(config)
        results = {}
        for job in make_jobs(config, source):
            result = load_job(job, today)
            totals = results.setdefault(job.source, {"saved": 0, "skipped": 0, "pairs": 0})
            totals["saved"] += result["saved"]
            totals["skipped"] += result["skipped"]
            totals["pairs"] += 1
        # Do not publish a run made against a reference that changed mid-load.
        if config != get_configuration():
            raise RuntimeError("Wordstat references changed during loading; rerun with the new configuration")
        validation = None
        rebuild = None
        synced = None
        demand_synced = None
        if source is None:
            validation = validate_download(config, today)
            if not validation["ok"]:
                raise RuntimeError(f"Wordstat load is incomplete: {validation}")
            from analytics.services.yd_wordstat_rebuild_sql import rebuild_yd_wordstat_for_from_raw_sql
            from analytics.services.yd_wordstat_sync import sync_yd_wordstat_to_clickhouse
            from dashboards.cache.invalidation import invalidate_dashboard_by_name

            rebuild = rebuild_yd_wordstat_for_from_raw_sql()
            synced = sync_yd_wordstat_to_clickhouse()
            # The statistics publication must invalidate even if demand rebuilding fails.
            invalidate_dashboard_by_name("Wordstat")
            notify_wordstat_updated()
            from analytics.services.wordstat_demand_mart import sync_wordstat_demand
            demand_synced = sync_wordstat_demand()
            notify_wordstat_updated()
            _notify("[b]Wordstat v2[/b] Загрузка и публикация завершены. Региональный срез: 7 групп IPLAST.")
        return {
            "status": "ok", "source": source or "full", "region_mode": "iplast",
            "region_check": region_check, "raw": results,
            "validation": validation, "rebuild": rebuild, "clickhouse": synced,
            "demand_clickhouse": demand_synced,
        }


def run_yd_wordstat_api_pipeline(source=None):
    if not settings.YD_WORDSTAT_V2_LOAD_ENABLED:
        raise RuntimeError("Wordstat v2 loading is disabled. Run the plan and probe before enabling YD_WORDSTAT_V2_LOAD_ENABLED.")
    try:
        return _run_pipeline(source)
    except Exception:
        logger.exception("Wordstat v2 load failed")
        _notify("[b]Wordstat v2[/b] Загрузка завершилась ошибкой. Подробности: api_yd_wordstat.log. Сохранённые запросы будут учтены при повторном запуске.")
        raise
