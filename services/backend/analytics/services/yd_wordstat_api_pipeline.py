import logging
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from datasets.models import (
    YdWordstatPhraseRef,
    YdWordstatDeviceRef,
    YdWordstatRegionRef,
    YdWordstatAllRaw,
    YdWordstatDeviceRaw,
    YdWordstatRegionRaw,
)
from datasets.services.external_api.yd_wordstat_api_client import (
    YdWordstatApiError,
    YdWordstatQuotaExceeded,
    fetch_yd_wordstat_user_info,
)
from datasets.services.external_api.yd_wordstat_api_loader import (
    YdWordstatApiLoadError,
    load_yd_wordstat_all_raw_from_api,
    load_yd_wordstat_device_raw_from_api,
    load_yd_wordstat_region_raw_from_api,
)
from datasets.services.external_api.yd_wordstat_region_ref_loader import (
    refresh_yd_wordstat_regions_from_api,
)

from analytics.services.yd_wordstat_rebuild_sql import (
    rebuild_yd_wordstat_for_from_raw_sql,
)
from analytics.services.yd_wordstat_sync import sync_yd_wordstat_to_clickhouse
from analytics.services.bitrix_notify import send_bitrix_message

from dashboards.cache.invalidation import invalidate_dashboard_by_name
from dashboards.realtime import notify_dashboard_updated


logger = logging.getLogger("external_api.yd_wordstat")


SOURCE_LOADERS = {
    "all": load_yd_wordstat_all_raw_from_api,
    "device": load_yd_wordstat_device_raw_from_api,
    "region": load_yd_wordstat_region_raw_from_api,
}


def get_setting_int(name: str, default: int) -> int:
    value = getattr(settings, name, default)

    try:
        return int(value)
    except Exception:
        return default


def seconds_until_next_day() -> int:
    now = timezone.localtime()
    tomorrow = now.date() + timedelta(days=1)

    resume_minutes = get_setting_int(
        "YD_WORDSTAT_QUOTA_RESUME_MINUTES_AFTER_MIDNIGHT",
        10,
    )

    next_run = timezone.make_aware(
        datetime.combine(tomorrow, datetime.min.time()),
        timezone.get_current_timezone(),
    ) + timedelta(minutes=resume_minutes)

    return max(60, int((next_run - now).total_seconds()))


def sleep_after_quota_exceeded(state: dict):
    max_quota_wait_days = get_setting_int(
        "YD_WORDSTAT_MAX_QUOTA_WAIT_DAYS",
        7,
    )

    state["quota_waits"] += 1

    if state["quota_waits"] > max_quota_wait_days:
        raise RuntimeError(
            "YD Wordstat quota wait limit exceeded: "
            f"{state['quota_waits']} waits, max={max_quota_wait_days}"
        )

    sleep_seconds = seconds_until_next_day()

    logger.info(
        "YD Wordstat quota exhausted. Waiting for next day: wait_number=%s/%s, seconds=%s",
        state["quota_waits"],
        max_quota_wait_days,
        sleep_seconds,
    )

    send_bitrix_message(
        f"[b]yd_wordstat API[/b]\n"
        f"Квота Wordstat закончилась.\n"
        f"Ожидание до нового дня: попытка {state['quota_waits']} из {max_quota_wait_days}.\n"
        f"Загрузка продолжится после 00:10.",
        logger_name="external_api.yd_wordstat",
    )

    time.sleep(sleep_seconds)


def sleep_after_api_error(state: dict, source: str, exc: Exception):
    max_api_error_waits = get_setting_int(
        "YD_WORDSTAT_MAX_API_ERROR_WAITS",
        12,
    )
    sleep_seconds = get_setting_int(
        "YD_WORDSTAT_API_ERROR_SLEEP_SECONDS",
        3600,
    )

    state["api_error_waits"] += 1

    if state["api_error_waits"] > max_api_error_waits:
        raise RuntimeError(
            "YD Wordstat API error wait limit exceeded: "
            f"{state['api_error_waits']} waits, max={max_api_error_waits}, "
            f"last_error={exc}"
        ) from exc

    logger.warning(
        "YD Wordstat API source failed. Waiting before retry: source=%s, wait_number=%s/%s, seconds=%s, error=%s",
        source,
        state["api_error_waits"],
        max_api_error_waits,
        sleep_seconds,
        exc,
    )

    send_bitrix_message(
        f"[b]yd_wordstat API[/b]\n"
        f"Ошибка ответа API Wordstat.\n"
        f"Источник: {source}\n"
        f"Пауза: {sleep_seconds // 60} мин.\n"
        f"Попытка ожидания: {state['api_error_waits']} из {max_api_error_waits}.\n"
        f"Ошибка: {exc}",
        logger_name="external_api.yd_wordstat",
    )

    time.sleep(sleep_seconds)


def run_yd_wordstat_region_ref_refresh_until_done(state: dict):
    attempts = 0

    while True:
        attempts += 1

        try:
            logger.info(
                "YD Wordstat region ref refresh started: attempt=%s",
                attempts,
            )

            quota = fetch_yd_wordstat_user_info()

            if quota["daily_limit_remaining"] == 0 or quota["daily_limit_remaining"] == "0":
                raise YdWordstatQuotaExceeded("YD Wordstat daily quota exhausted")

            result = refresh_yd_wordstat_regions_from_api()

            logger.info(
                "YD Wordstat region ref refresh finished: attempts=%s, result=%s",
                attempts,
                result,
            )

            return {
                "status": "ok",
                "attempts": attempts,
                "result": result,
            }

        except YdWordstatQuotaExceeded:
            logger.info("YD Wordstat quota exhausted while refreshing region ref")
            sleep_after_quota_exceeded(state)

        except YdWordstatApiError as exc:
            logger.exception("YD Wordstat region ref refresh API error")
            sleep_after_api_error(state, "region_ref", exc)


def run_yd_wordstat_api_source_until_done(source: str, state: dict):
    if source not in SOURCE_LOADERS:
        raise ValueError("source must be one of: all, device, region")

    loader = SOURCE_LOADERS[source]
    attempts = 0

    while True:
        attempts += 1

        try:
            logger.info(
                "YD Wordstat API source load started: source=%s, attempt=%s",
                source,
                attempts,
            )

            quota = fetch_yd_wordstat_user_info()

            if quota["daily_limit_remaining"] == 0 or quota["daily_limit_remaining"] == "0":
                raise YdWordstatQuotaExceeded("YD Wordstat daily quota exhausted")

            result = loader()

            logger.info(
                "YD Wordstat API source load finished: source=%s, attempts=%s, result=%s",
                source,
                attempts,
                result,
            )

            return {
                "status": "ok",
                "source": source,
                "attempts": attempts,
                "result": result,
            }

        except YdWordstatQuotaExceeded:
            logger.info(
                "YD Wordstat quota exhausted while loading source=%s",
                source,
            )
            sleep_after_quota_exceeded(state)

        except (YdWordstatApiLoadError, YdWordstatApiError) as exc:
            logger.exception(
                "YD Wordstat API load error while loading source=%s",
                source,
            )
            sleep_after_api_error(state, source, exc)


def get_previous_month_first_day():
    today = timezone.localdate()
    first_day_current_month = today.replace(day=1)
    previous_month_last_day = first_day_current_month - timedelta(days=1)

    return previous_month_last_day.replace(day=1)


def count_distinct(model, field: str, filters: dict | None = None) -> int:
    queryset = model.objects.all()

    if filters:
        queryset = queryset.filter(**filters)

    return queryset.values(field).distinct().count()


def add_check(checks: list[dict], name: str, ok: bool, ok_message: str, fail_message: str):
    checks.append(
        {
            "name": name,
            "ok": ok,
            "message": ok_message if ok else fail_message,
        }
    )


def validate_yd_wordstat_download_completeness():
    """
    Проверка полноты скачивания перед rebuild.

    Если проверка не пройдена, rebuild и sync не запускаем,
    чтобы пользователь не увидел частично обновленные данные.
    """

    today = timezone.localdate()
    previous_month_first_day = get_previous_month_first_day()

    checks = []

    current_month_filters = {
        "date_add__year": today.year,
        "date_add__month": today.month,
    }

    phrase_count = count_distinct(YdWordstatPhraseRef, "phrase")
    device_count = count_distinct(YdWordstatDeviceRef, "device")

    region_queryset = YdWordstatRegionRef.objects.filter(
        Q(country_label="Россия") | Q(region_value=166)
    )
    region_count = region_queryset.values("region_value").distinct().count()

    all_current_exists = YdWordstatAllRaw.objects.filter(
        **current_month_filters,
    ).exists()
    device_current_exists = YdWordstatDeviceRaw.objects.filter(
        **current_month_filters,
    ).exists()
    region_current_exists = YdWordstatRegionRaw.objects.filter(
        **current_month_filters,
    ).exists()
    region_ref_current_exists = YdWordstatRegionRef.objects.filter(
        **current_month_filters,
    ).exists()

    add_check(
        checks,
        "all_date_add_current_month",
        all_current_exists,
        "yd_wordstat_all обновилась в текущем месяце",
        "yd_wordstat_all не обновилась в текущем месяце",
    )

    add_check(
        checks,
        "device_date_add_current_month",
        device_current_exists,
        "yd_wordstat_device обновилась в текущем месяце",
        "yd_wordstat_device не обновилась в текущем месяце",
    )

    add_check(
        checks,
        "region_date_add_current_month",
        region_current_exists,
        "yd_wordstat_region обновилась в текущем месяце",
        "yd_wordstat_region не обновилась в текущем месяце",
    )

    add_check(
        checks,
        "region_ref_date_add_current_month",
        region_ref_current_exists,
        "yd_wordstat_ref_region обновилась в текущем месяце",
        "yd_wordstat_ref_region не обновилась в текущем месяце",
    )

    all_phrase_loaded = count_distinct(
        YdWordstatAllRaw,
        "phrase",
        current_month_filters,
    )
    device_phrase_loaded = count_distinct(
        YdWordstatDeviceRaw,
        "phrase",
        current_month_filters,
    )
    region_phrase_loaded = count_distinct(
        YdWordstatRegionRaw,
        "phrase",
        current_month_filters,
    )

    add_check(
        checks,
        "all_phrase_count",
        all_phrase_loaded >= phrase_count,
        f"yd_wordstat_all: все фразы добавлены ({all_phrase_loaded}/{phrase_count})",
        f"yd_wordstat_all: не все фразы добавлены ({all_phrase_loaded}/{phrase_count})",
    )

    add_check(
        checks,
        "device_phrase_count",
        device_phrase_loaded >= phrase_count,
        f"yd_wordstat_device: все фразы добавлены ({device_phrase_loaded}/{phrase_count})",
        f"yd_wordstat_device: не все фразы добавлены ({device_phrase_loaded}/{phrase_count})",
    )

    add_check(
        checks,
        "region_phrase_count",
        region_phrase_loaded >= phrase_count,
        f"yd_wordstat_region: все фразы добавлены ({region_phrase_loaded}/{phrase_count})",
        f"yd_wordstat_region: не все фразы добавлены ({region_phrase_loaded}/{phrase_count})",
    )

    device_loaded = count_distinct(
        YdWordstatDeviceRaw,
        "device",
        current_month_filters,
    )
    region_loaded = count_distinct(
        YdWordstatRegionRaw,
        "region_value",
        current_month_filters,
    )

    add_check(
        checks,
        "device_count",
        device_loaded >= device_count,
        f"yd_wordstat_device: все устройства добавлены ({device_loaded}/{device_count})",
        f"yd_wordstat_device: не все устройства добавлены ({device_loaded}/{device_count})",
    )

    add_check(
        checks,
        "region_count",
        region_loaded >= region_count,
        f"yd_wordstat_region: все регионы добавлены ({region_loaded}/{region_count})",
        f"yd_wordstat_region: не все регионы добавлены ({region_loaded}/{region_count})",
    )

    all_previous_month_exists = YdWordstatAllRaw.objects.filter(
        date=previous_month_first_day,
    ).exists()
    device_previous_month_exists = YdWordstatDeviceRaw.objects.filter(
        date=previous_month_first_day,
    ).exists()
    region_previous_month_exists = YdWordstatRegionRaw.objects.filter(
        date=previous_month_first_day,
    ).exists()

    add_check(
        checks,
        "all_previous_month",
        all_previous_month_exists,
        f"yd_wordstat_all: данные за предыдущий месяц присутствуют ({previous_month_first_day})",
        f"yd_wordstat_all: отсутствуют данные за предыдущий месяц ({previous_month_first_day})",
    )

    add_check(
        checks,
        "device_previous_month",
        device_previous_month_exists,
        f"yd_wordstat_device: данные за предыдущий месяц присутствуют ({previous_month_first_day})",
        f"yd_wordstat_device: отсутствуют данные за предыдущий месяц ({previous_month_first_day})",
    )

    add_check(
        checks,
        "region_previous_month",
        region_previous_month_exists,
        f"yd_wordstat_region: данные за предыдущий месяц присутствуют ({previous_month_first_day})",
        f"yd_wordstat_region: отсутствуют данные за предыдущий месяц ({previous_month_first_day})",
    )

    failed_checks = [
        item
        for item in checks
        if not item["ok"]
    ]

    status = "ok" if not failed_checks else "failed"

    result = {
        "status": status,
        "ok": status == "ok",
        "checks": checks,
        "failed_checks": failed_checks,
        "expected": {
            "phrases": phrase_count,
            "devices": device_count,
            "regions": region_count,
        },
        "loaded_current_month": {
            "all_phrases": all_phrase_loaded,
            "device_phrases": device_phrase_loaded,
            "region_phrases": region_phrase_loaded,
            "devices": device_loaded,
            "regions": region_loaded,
        },
        "previous_month_first_day": previous_month_first_day.isoformat(),
    }

    lines = []

    for item in checks:
        mark = "OK" if item["ok"] else "ERROR"
        lines.append(f"{mark}: {item['message']}")

    message = (
        f"[b]yd_wordstat API: проверка полноты[/b]\n"
        f"Статус: {'OK' if result['ok'] else 'НЕ OK'}\n"
        f"Предыдущий месяц: {previous_month_first_day}\n"
        f"Фразы в справочнике: {phrase_count}\n"
        f"Устройства в справочнике: {device_count}\n"
        f"Регионы к загрузке: {region_count}\n\n"
        + "\n".join(lines)
    )

    send_bitrix_message(
        message,
        logger_name="external_api.yd_wordstat",
    )

    logger.info("YD Wordstat completeness validation finished: %s", result)

    return result


def run_yd_wordstat_api_pipeline(source: str | None = None):
    """
    source=None:
        Полный запуск:
        region_ref -> all -> device -> region -> validation -> rebuild -> sync -> cache invalidate -> websocket.

    source='all' / 'device' / 'region':
        Ручной запуск одного среза.
        Validation, rebuild и ClickHouse sync НЕ выполняются.
    """

    logger.info("YD Wordstat API pipeline started: source=%s", source)

    state = {
        "quota_waits": 0,
        "api_error_waits": 0,
    }

    try:
        region_ref_result = None

        if source is None:
            sources = ["all", "device", "region"]
            run_rebuild = True

            region_ref_result = run_yd_wordstat_region_ref_refresh_until_done(
                state=state,
            )
        else:
            sources = [source]
            run_rebuild = False

        raw_results = {}

        for item in sources:
            raw_results[item] = run_yd_wordstat_api_source_until_done(
                source=item,
                state=state,
            )

        validation_result = None
        rebuild_result = None
        clickhouse_result = None

        if run_rebuild:
            validation_result = validate_yd_wordstat_download_completeness()

            if not validation_result["ok"]:
                raise RuntimeError(
                    "YD Wordstat completeness validation failed. "
                    "Rebuild and ClickHouse sync were skipped."
                )

            rebuild_result = rebuild_yd_wordstat_for_from_raw_sql()
            clickhouse_result = sync_yd_wordstat_to_clickhouse()

            invalidate_dashboard_by_name("Wordstat")
            notify_dashboard_updated("Wordstat")

            send_bitrix_message(
                f"[b]yd_wordstat API[/b]\n"
                f"Загрузка Wordstat полностью завершена.\n"
                f"Проверка полноты: OK.\n"
                f"Срезы: all, device, region.\n"
                f"Ожиданий квоты: {state['quota_waits']}.\n"
                f"Ожиданий после ошибок API: {state['api_error_waits']}.\n"
                f"ClickHouse: {clickhouse_result}",
                logger_name="external_api.yd_wordstat",
            )

        result = {
            "status": "ok",
            "source": "api",
            "requested_source": source,
            "full_run": source is None,
            "region_ref": region_ref_result,
            "raw": raw_results,
            "validation": validation_result,
            "rebuild": rebuild_result,
            "clickhouse": clickhouse_result,
            "quota_waits": state["quota_waits"],
            "api_error_waits": state["api_error_waits"],
        }

        logger.info("YD Wordstat API pipeline finished: %s", result)

        return result

    except Exception as exc:
        logger.exception("YD Wordstat API pipeline failed")

        send_bitrix_message(
            f"[b]yd_wordstat API[/b]\n"
            f"Ошибка API-загрузки Wordstat.\n"
            f"Источник: {source or 'full'}\n"
            f"Ожиданий квоты: {state['quota_waits']}.\n"
            f"Ожиданий после ошибок API: {state['api_error_waits']}.\n"
            f"Ошибка: {exc}",
            logger_name="external_api.yd_wordstat",
        )

        raise