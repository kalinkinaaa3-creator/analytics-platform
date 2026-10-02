from analytics.services.bitrix_notify import send_bitrix_message
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from datasets.models import NomenclaturePrice
from .nomenclature_load_lock import serialized_nomenclature_day
from datasets.services.external_api.price_api_client import (
    fetch_price_api_rows,
)


logger = logging.getLogger("external_api.price")


PRICE_INITIAL_DATE = date(2026, 1, 1)


def clean_str(value, default=None):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def clean_int(value, default=None):
    """
    Корректно обрабатывает:
    131641
    "131641"
    "00000131641"
    "20"
    20.0
    "20.0"
    """
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    value = (
        value
        .replace(" ", "")
        .replace("\xa0", "")
        .replace(",", ".")
    )

    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def clean_decimal(value, default=None):
    """
    Корректно обрабатывает:
    39924.5
    "39924.5"
    "39924,5"
    "39 924,50"
    null
    """
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    value = (
        value
        .replace(" ", "")
        .replace("\xa0", "")
        .replace(",", ".")
    )

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return default


def normalize_price_record(record: dict, load_date: date) -> NomenclaturePrice:
    return NomenclaturePrice(
        date=load_date,

        shipp_region=clean_str(record.get("shipp_region")),
        nom_group=clean_str(record.get("nom_group")),
        price_list=clean_str(record.get("price_list")),
        nom=clean_str(record.get("nom")),

        code=clean_int(record.get("code"), default=0),

        vat=clean_int(record.get("VAT")),

        distr=clean_decimal(record.get("distr")),
        distr_1=clean_decimal(record.get("distr_1")),
        retail=clean_decimal(record.get("retail")),
        small=clean_decimal(record.get("small")),
        medium=clean_decimal(record.get("medium")),
        large=clean_decimal(record.get("large")),
        base=clean_decimal(record.get("base")),
    )


def get_price_load_period(end_date=None):
    today = end_date or date.today()

    max_date = NomenclaturePrice.objects.aggregate(
        max_date=Max("date")
    )["max_date"]

    logger.info(
        "NomenclaturePrice current max date: %s",
        max_date,
    )

    if max_date is None:
        start_date = PRICE_INITIAL_DATE

    elif max_date >= today:
        # Если сегодняшний день уже есть,
        # перезагружаем его полностью.
        start_date = today

    else:
        start_date = max_date + timedelta(days=1)

    logger.info(
        "NomenclaturePrice load period: start_date=%s end_date=%s",
        start_date,
        today,
    )

    return start_date, today


def iter_dates(start_date: date, end_date: date):
    current_date = start_date

    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


@serialized_nomenclature_day
def load_price_day(load_date: date) -> dict:
    """
    Загружает и полностью заменяет данные одного дня.

    Сначала API и нормализация.
    Только после успешного получения данных удаляется старая версия дня.
    """
    logger.info(
        "NomenclaturePrice day load started: date=%s",
        load_date,
    )

    rows = fetch_price_api_rows(load_date)

    logger.info(
        "NomenclaturePrice API rows received: date=%s rows=%s",
        load_date,
        len(rows),
    )

    # Пока считаем пустой ответ подозрительным.
    # Это защищает от удаления существующих данных при сбое 1С.
    if not rows:
        raise ValueError(
            f"Price API returned empty list for {load_date}. "
            "Existing data for this date will not be deleted."
        )

    objects = [
        normalize_price_record(
            record=record,
            load_date=load_date,
        )
        for record in rows
    ]

    # Записи без нормального кода номенклатуры не сохраняем.
    valid_objects = [
        obj
        for obj in objects
        if obj.code
    ]

    skipped = len(objects) - len(valid_objects)

    logger.info(
        "NomenclaturePrice normalize finished: "
        "date=%s objects=%s skipped=%s",
        load_date,
        len(valid_objects),
        skipped,
    )

    if not valid_objects:
        raise ValueError(
            f"Price API returned no valid price rows for {load_date}. "
            "Existing data for this date will not be deleted."
        )

    with transaction.atomic():
        deleted_count, _ = NomenclaturePrice.objects.filter(
            date=load_date,
        ).delete()

        logger.info(
            "NomenclaturePrice deleted old rows: date=%s rows=%s",
            load_date,
            deleted_count,
        )

        NomenclaturePrice.objects.bulk_create(
            valid_objects,
            batch_size=5000,
        )

        logger.info(
            "NomenclaturePrice inserted rows: date=%s rows=%s",
            load_date,
            len(valid_objects),
        )

    result = {
        "date": load_date.isoformat(),
        "received": len(rows),
        "saved": len(valid_objects),
        "skipped": skipped,
        "deleted": deleted_count,
    }

    logger.info(
        "NomenclaturePrice day load finished: %s",
        result,
    )

    return result


def load_prices_from_api(
    start_date=None,
    end_date=None,
) -> dict:
    try:
        logger.info("NomenclaturePrice API load started")

        if start_date is None:
            start_date, calculated_end_date = get_price_load_period(
                end_date=end_date,
            )

            if end_date is None:
                end_date = calculated_end_date

        elif end_date is None:
            end_date = date.today()

        if start_date > end_date:
            logger.info(
                "NomenclaturePrice API load skipped: "
                "start_date=%s > end_date=%s",
                start_date,
                end_date,
            )

            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": 0,
                "received": 0,
                "saved": 0,
                "skipped": 0,
                "deleted": 0,
            }

        total_days = 0
        total_received = 0
        total_saved = 0
        total_skipped = 0
        total_deleted = 0
        day_results = []

        for load_date in iter_dates(start_date, end_date):
            # Если конкретный день падает —
            # исключение специально НЕ подавляем.
            # Загрузка останавливается на проблемной дате.
            day_result = load_price_day(load_date)

            day_results.append(day_result)

            total_days += 1
            total_received += day_result["received"]
            total_saved += day_result["saved"]
            total_skipped += day_result["skipped"]
            total_deleted += day_result["deleted"]

        result = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": total_days,
            "received": total_received,
            "saved": total_saved,
            "skipped": total_skipped,
            "deleted": total_deleted,
            "day_results": day_results,
        }

        logger.info(
            "NomenclaturePrice API load finished: "
            "start_date=%s end_date=%s days=%s "
            "received=%s saved=%s skipped=%s deleted=%s",
            start_date,
            end_date,
            total_days,
            total_received,
            total_saved,
            total_skipped,
            total_deleted,
        )

        from sales_calculator.refresh import source_updated
        source_updated("price")
        return result
    except Exception:
        logger.exception("Nomenclature prices API load failed")
        send_bitrix_message("[b]Nomenclature prices API[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 load_prices_from_api.", logger_name=logger.name)
        raise
