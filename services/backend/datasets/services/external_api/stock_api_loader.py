from analytics.services.bitrix_notify import send_bitrix_message
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from datasets.models import NomenclatureStock
from datasets.services.external_api.stock_api_client import (
    fetch_stock_api_rows,
)


logger = logging.getLogger("external_api.stock")


STOCK_INITIAL_DATE = date(2026, 9, 24)


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


def normalize_stock_record(record: dict, load_date: date) -> NomenclatureStock:
    # As with prices, date_1C is not used: store the requested reporting date.
    return NomenclatureStock(
        date=load_date,
        warehouse=clean_str(record.get("warehouse")),
        nom_code=clean_int(record.get("nom_code"), default=0),
        nomenclature=clean_str(record.get("nomenclature")),
        quantity=clean_decimal(record.get("quantity")),
        stock=clean_decimal(record.get("stock")),
        dev_maximum=clean_decimal(record.get("dev_maximum")),
    )


def get_stock_load_period(end_date=None):
    today = end_date or date.today()

    max_date = NomenclatureStock.objects.aggregate(
        max_date=Max("date")
    )["max_date"]

    logger.info(
        "NomenclatureStock current max date: %s",
        max_date,
    )

    if max_date is None:
        start_date = STOCK_INITIAL_DATE

    elif max_date >= today:
        # Если сегодняшний день уже есть,
        # перезагружаем его полностью.
        start_date = today

    else:
        start_date = max_date + timedelta(days=1)

    logger.info(
        "NomenclatureStock load period: start_date=%s end_date=%s",
        start_date,
        today,
    )

    return start_date, today


def iter_dates(start_date: date, end_date: date):
    current_date = start_date

    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def load_stock_day(load_date: date) -> dict:
    """
    Загружает и полностью заменяет данные одного дня.

    Сначала API и нормализация.
    Только после успешного получения данных удаляется старая версия дня.
    """
    logger.info(
        "NomenclatureStock day load started: date=%s",
        load_date,
    )

    rows = fetch_stock_api_rows(load_date)

    logger.info(
        "NomenclatureStock API rows received: date=%s rows=%s",
        load_date,
        len(rows),
    )

    # Пока считаем пустой ответ подозрительным.
    # Это защищает от удаления существующих данных при сбое 1С.
    if not rows:
        raise ValueError(
            f"Stock API returned empty list for {load_date}. "
            "Existing data for this date will not be deleted."
        )

    objects = [
        normalize_stock_record(
            record=record,
            load_date=load_date,
        )
        for record in rows
    ]

    # Записи без нормального кода номенклатуры не сохраняем.
    valid_objects = [
        obj
        for obj in objects
        if obj.nom_code
    ]

    skipped = len(objects) - len(valid_objects)

    logger.info(
        "NomenclatureStock normalize finished: "
        "date=%s objects=%s skipped=%s",
        load_date,
        len(valid_objects),
        skipped,
    )

    if not valid_objects:
        raise ValueError(
            f"Stock API returned no valid stock rows for {load_date}. "
            "Existing data for this date will not be deleted."
        )

    with transaction.atomic():
        deleted_count, _ = NomenclatureStock.objects.filter(
            date=load_date,
        ).delete()

        logger.info(
            "NomenclatureStock deleted old rows: date=%s rows=%s",
            load_date,
            deleted_count,
        )

        NomenclatureStock.objects.bulk_create(
            valid_objects,
            batch_size=5000,
        )

        logger.info(
            "NomenclatureStock inserted rows: date=%s rows=%s",
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
        "NomenclatureStock day load finished: %s",
        result,
    )

    return result


def load_stocks_from_api(
    start_date=None,
    end_date=None,
) -> dict:
    try:
        logger.info("NomenclatureStock API load started")

        if start_date is None:
            start_date, calculated_end_date = get_stock_load_period(
                end_date=end_date,
            )

            if end_date is None:
                end_date = calculated_end_date

        elif end_date is None:
            end_date = date.today()

        if start_date > end_date:
            logger.info(
                "NomenclatureStock API load skipped: "
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
            day_result = load_stock_day(load_date)

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
            "NomenclatureStock API load finished: "
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

        return result
    except Exception:
        logger.exception("Nomenclature stocks API load failed")
        send_bitrix_message("[b]Nomenclature stocks API[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 load_stocks_from_api.", logger_name=logger.name)
        raise
