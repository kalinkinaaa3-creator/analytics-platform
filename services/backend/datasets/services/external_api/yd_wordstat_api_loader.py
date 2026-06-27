import logging
from datetime import date, datetime

from django.db import transaction

from datasets.models import (
    YdWordstatPhraseRef,
    YdWordstatDeviceRef,
    YdWordstatRegionRef,
    YdWordstatIplastRegionRef,
    YdWordstatAllRaw,
    YdWordstatDeviceRaw,
    YdWordstatRegionRaw,
)
from datasets.services.external_api.yd_wordstat_api_client import (
    fetch_yd_wordstat_dynamics,
    YdWordstatQuotaExceeded,
)
from datasets.services.external_api.yd_wordstat_load_period import (
    get_reload_period_without_delete,
    has_current_month_loaded,
)




logger = logging.getLogger("external_api.yd_wordstat")


MAX_RETRIES = 3
BATCH_SIZE = 5000


class YdWordstatApiLoadError(Exception):
    pass


def clean_str(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_int(value, default=0):
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def clean_date(value):
    if value is None:
        return None

    if isinstance(value, date):
        return value

    value = str(value).strip()

    if value == "":
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    return None


def get_phrase_refs():
    return list(
        YdWordstatPhraseRef.objects
        .exclude(phrase__isnull=True)
        .exclude(phrase="")
        .order_by("phrase")
        .values("phrase", "feature", "category")
    )


def get_device_refs():
    return list(
        YdWordstatDeviceRef.objects
        .exclude(device__isnull=True)
        .exclude(device="")
        .order_by("device")
        .values_list("device", flat=True)
    )


def get_region_refs_for_loading():
    return list(
        YdWordstatRegionRef.objects
        .filter(country_label="Россия")
        .values(
            "region_value",
            "region_label",
            "country_label",
            "macroregion_label",
        )
    ) + list(
        YdWordstatRegionRef.objects
        .filter(region_value=166)
        .exclude(country_label="Россия")
        .values(
            "region_value",
            "region_label",
            "country_label",
            "macroregion_label",
        )
    )


def get_iplast_region_map():
    return {
        item["region_value"]: item["macroregion_label"]
        for item in YdWordstatIplastRegionRef.objects.values(
            "region_value",
            "macroregion_label",
        )
    }


def parse_dynamics_response(data):
    request_phrase = clean_str(data.get("requestPhrase"))
    dynamics = data.get("dynamics") or []

    if not isinstance(dynamics, list):
        dynamics = []

    return request_phrase, dynamics


def fetch_with_retry(
    phrase: str,
    date_start,
    date_finish,
    devices: list[str] | None = None,
    regions: list[int] | None = None,
):
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_yd_wordstat_dynamics(
                phrase=phrase,
                date_start=date_start,
                date_finish=date_finish,
                devices=devices,
                regions=regions,
            )

        except YdWordstatQuotaExceeded:
            logger.info(
                "YD Wordstat quota exhausted during request: phrase=%s, devices=%s, regions=%s",
                phrase,
                devices,
                regions,
            )
            raise

        except Exception as exc:
            last_error = exc

            logger.exception(
                "YD Wordstat API attempt failed: attempt=%s/%s, phrase=%s, devices=%s, regions=%s",
                attempt,
                MAX_RETRIES,
                phrase,
                devices,
                regions,
            )

    raise YdWordstatApiLoadError(
        f"YD Wordstat API failed after {MAX_RETRIES} attempts: "
        f"phrase={phrase}, devices={devices}, regions={regions}, error={last_error}"
    )


def save_objects_after_success(model, filters: dict, reload_from_date, objects: list):
    """
    Безопасное переудаление:
    API уже успешно отработал, объекты уже собраны.
    Только теперь удаляем старый диапазон и вставляем новые строки.
    """

    if not objects:
        logger.warning(
            "YD Wordstat save skipped because objects list is empty: model=%s, filters=%s, reload_from_date=%s",
            model.__name__,
            filters,
            reload_from_date,
        )

        return 0, 0

    with transaction.atomic():
        deleted_count, _ = model.objects.filter(
            **filters,
            date__gte=reload_from_date,
        ).delete()

        model.objects.bulk_create(
            objects,
            batch_size=BATCH_SIZE,
        )

    return deleted_count, len(objects)


def load_yd_wordstat_all_raw_from_api(today: date | None = None):
    logger.info("YD Wordstat all raw API load started")

    phrase_refs = get_phrase_refs()

    total_received = 0
    total_saved = 0
    total_deleted = 0
    total_skipped = 0

    for phrase_ref in phrase_refs:
        phrase = phrase_ref["phrase"]
        filters = {"phrase": phrase}

        if has_current_month_loaded(
            model=YdWordstatAllRaw,
            filters=filters,
            today=today,
        ):
            total_skipped += 1
            logger.info("YD Wordstat all skipped, already loaded: phrase=%s", phrase)
            continue

        period = get_reload_period_without_delete(
            model=YdWordstatAllRaw,
            filters=filters,
            today=today,
        )

        if period["skipped"]:
            total_skipped += 1
            logger.info(
                "YD Wordstat all skipped by period: phrase=%s, period=%s",
                phrase,
                period,
            )
            continue

        data = fetch_with_retry(
            phrase=phrase,
            date_start=period["date_start"],
            date_finish=period["date_finish"],
            devices=["all"],
        )

        request_phrase, dynamics = parse_dynamics_response(data)
        total_received += len(dynamics)

        objects = []

        for item in dynamics:
            row_date = clean_date(item.get("date"))
            row_count = item.get("count")

            if not row_date:
                continue

            objects.append(
                YdWordstatAllRaw(
                    phrase=request_phrase or phrase,
                    date=row_date,
                    count=clean_int(row_count),
                    feature=phrase_ref["feature"],
                    category=phrase_ref["category"],
                )
            )

        deleted_count, saved_count = save_objects_after_success(
            model=YdWordstatAllRaw,
            filters=filters,
            reload_from_date=period["reload_from_date"],
            objects=objects,
        )

        total_deleted += deleted_count
        total_saved += saved_count

        logger.info(
            "YD Wordstat all phrase loaded: phrase=%s, received=%s, saved=%s, deleted=%s",
            phrase,
            len(dynamics),
            saved_count,
            deleted_count,
        )

    result = {
        "received": total_received,
        "saved": total_saved,
        "deleted": total_deleted,
        "skipped": total_skipped,
        "phrases": len(phrase_refs),
    }

    logger.info("YD Wordstat all raw API load finished: %s", result)

    return result


def load_yd_wordstat_device_raw_from_api(today: date | None = None):
    logger.info("YD Wordstat device raw API load started")

    phrase_refs = get_phrase_refs()
    devices = get_device_refs()

    total_received = 0
    total_saved = 0
    total_deleted = 0
    total_skipped = 0
    total_pairs = 0

    for device in devices:
        for phrase_ref in phrase_refs:
            phrase = phrase_ref["phrase"]
            total_pairs += 1

            filters = {
                "phrase": phrase,
                "device": device,
            }

            if has_current_month_loaded(
                model=YdWordstatDeviceRaw,
                filters=filters,
                today=today,
            ):
                total_skipped += 1
                logger.info(
                    "YD Wordstat device skipped, already loaded: phrase=%s, device=%s",
                    phrase,
                    device,
                )
                continue

            period = get_reload_period_without_delete(
                model=YdWordstatDeviceRaw,
                filters=filters,
                today=today,
            )

            if period["skipped"]:
                total_skipped += 1
                logger.info(
                    "YD Wordstat device skipped by period: phrase=%s, device=%s, period=%s",
                    phrase,
                    device,
                    period,
                )
                continue

            data = fetch_with_retry(
                phrase=phrase,
                date_start=period["date_start"],
                date_finish=period["date_finish"],
                devices=[device],
            )

            request_phrase, dynamics = parse_dynamics_response(data)
            total_received += len(dynamics)

            objects = []

            for item in dynamics:
                row_date = clean_date(item.get("date"))
                row_count = item.get("count")

                if not row_date:
                    continue

                objects.append(
                    YdWordstatDeviceRaw(
                        phrase=request_phrase or phrase,
                        device=device,
                        date=row_date,
                        count=clean_int(row_count),
                        feature=phrase_ref["feature"],
                        category=phrase_ref["category"],
                    )
                )

            deleted_count, saved_count = save_objects_after_success(
                model=YdWordstatDeviceRaw,
                filters=filters,
                reload_from_date=period["reload_from_date"],
                objects=objects,
            )

            total_deleted += deleted_count
            total_saved += saved_count

            logger.info(
                "YD Wordstat device pair loaded: phrase=%s, device=%s, received=%s, saved=%s, deleted=%s",
                phrase,
                device,
                len(dynamics),
                saved_count,
                deleted_count,
            )

    result = {
        "received": total_received,
        "saved": total_saved,
        "deleted": total_deleted,
        "skipped": total_skipped,
        "phrases": len(phrase_refs),
        "devices": len(devices),
        "pairs": total_pairs,
    }

    logger.info("YD Wordstat device raw API load finished: %s", result)

    return result


def load_yd_wordstat_region_raw_from_api(today: date | None = None):
    logger.info("YD Wordstat region raw API load started")

    phrase_refs = get_phrase_refs()
    regions = get_region_refs_for_loading()
    iplast_region_map = get_iplast_region_map()

    total_received = 0
    total_saved = 0
    total_deleted = 0
    total_skipped = 0
    total_pairs = 0

    for phrase_ref in phrase_refs:
        phrase = phrase_ref["phrase"]

        for region in regions:
            region_value = region["region_value"]
            total_pairs += 1

            if region_value is None:
                total_skipped += 1
                continue

            filters = {
                "phrase": phrase,
                "region_value": region_value,
            }

            if has_current_month_loaded(
                model=YdWordstatRegionRaw,
                filters=filters,
                today=today,
            ):
                total_skipped += 1
                logger.info(
                    "YD Wordstat region skipped, already loaded: phrase=%s, region_value=%s",
                    phrase,
                    region_value,
                )
                continue

            period = get_reload_period_without_delete(
                model=YdWordstatRegionRaw,
                filters=filters,
                today=today,
            )

            if period["skipped"]:
                total_skipped += 1
                logger.info(
                    "YD Wordstat region skipped by period: phrase=%s, region_value=%s, period=%s",
                    phrase,
                    region_value,
                    period,
                )
                continue

            data = fetch_with_retry(
                phrase=phrase,
                date_start=period["date_start"],
                date_finish=period["date_finish"],
                devices=["all"],
                regions=[region_value],
            )

            request_phrase, dynamics = parse_dynamics_response(data)
            total_received += len(dynamics)

            objects = []

            for item in dynamics:
                row_date = clean_date(item.get("date"))
                row_count = item.get("count")

                if not row_date:
                    continue

                objects.append(
                    YdWordstatRegionRaw(
                        phrase=request_phrase or phrase,
                        region_label=region["region_label"],
                        region_value=region_value,
                        date=row_date,
                        count=clean_int(row_count),
                        feature=phrase_ref["feature"],
                        category=phrase_ref["category"],
                        country_label=region["country_label"],
                        macroregion_label=region["macroregion_label"],
                        macroregion_iplast=iplast_region_map.get(region_value),
                    )
                )

            deleted_count, saved_count = save_objects_after_success(
                model=YdWordstatRegionRaw,
                filters=filters,
                reload_from_date=period["reload_from_date"],
                objects=objects,
            )

            total_deleted += deleted_count
            total_saved += saved_count

            logger.info(
                "YD Wordstat region pair loaded: phrase=%s, region_value=%s, received=%s, saved=%s, deleted=%s",
                phrase,
                region_value,
                len(dynamics),
                saved_count,
                deleted_count,
            )

    result = {
        "received": total_received,
        "saved": total_saved,
        "deleted": total_deleted,
        "skipped": total_skipped,
        "phrases": len(phrase_refs),
        "regions": len(regions),
        "pairs": total_pairs,
    }

    logger.info("YD Wordstat region raw API load finished: %s", result)

    return result