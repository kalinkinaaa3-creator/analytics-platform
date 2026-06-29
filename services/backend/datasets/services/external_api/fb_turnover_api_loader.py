import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from datasets.models import TurnoverRaw
from datasets.services.external_api.fb_turnover_api_client import (
    fetch_fb_turnover_api_rows,
)


logger = logging.getLogger("external_api.fb_turnover")


def clean_str(value, default="-"):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def clean_int(value, default=0):
    if value is None or value == "":
        return default

    try:
        return int(float(str(value).replace(" ", "").replace("\xa0", "")))
    except Exception:
        return default


def clean_decimal(value, default=Decimal("0")):
    if value is None or value == "":
        return default

    value = str(value).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")

    try:
        return Decimal(value)
    except InvalidOperation:
        return default


def clean_date(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    if value[:10] == "0001-01-01":
        return None

    formats = [
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ]

    for fmt in formats:
        try:
            if fmt == "%Y%m%d":
                return datetime.strptime(value[:8], fmt).date()
            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    return None


def first_day_of_month(value: date) -> date:
    return value.replace(day=1)


def last_day_of_month(value: date) -> date:
    next_month = value.replace(day=28) + timedelta(days=4)
    return next_month.replace(day=1) - timedelta(days=1)


def add_month(value: date) -> date:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1)

    return value.replace(month=value.month + 1, day=1)


def get_turnover_load_period(end_date=None):
    current_date = date.today()
    end_date = end_date or last_day_of_month(current_date)

    max_date = TurnoverRaw.objects.aggregate(
        max_date=Max("date_start")
    )["max_date"]

    logger.info("TurnoverRaw current max date_start: %s", max_date)

    if max_date is None:
        start_date = date(2025, 1, 1)
    else:
        start_date = first_day_of_month(max_date - timedelta(days=33))

    return start_date, end_date


def normalize_turnover_record(record, fallback_date_start):
    date_stock = clean_date(record.get("date_stock"))
    date_end = clean_date(record.get("date_end"))

    return TurnoverRaw(
        date_stock=date_stock,
        date_start=fallback_date_start,
        date_end=date_end,

        warehouse_group=clean_str(record.get("warehouse_group")),
        warehouse=clean_str(record.get("warehouse")),
        nomenclature=clean_str(record.get("nomenclature")),

        quantity=clean_str(record.get("quantity")),
        price=clean_decimal(record.get("price")),
        amount_day=clean_int(record.get("amount_day")),

        middle_stock=clean_decimal(record.get("middle_stock")),
        middle_rubstock=clean_decimal(record.get("middle_rubstock")),
    )


def load_turnover_raw_from_api(start_date=None, end_date=None):
    logger.info("TurnoverRaw API load started")

    if start_date is None or end_date is None:
        start_date, end_date = get_turnover_load_period(end_date=end_date)

    if start_date > end_date:
        logger.info(
            "TurnoverRaw API load skipped: start_date=%s > end_date=%s",
            start_date,
            end_date,
        )

        return {
            "received": 0,
            "saved": 0,
            "deleted": 0,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "skipped": True,
        }

    logger.info(
        "TurnoverRaw API load period: start_date=%s, end_date=%s",
        start_date,
        end_date,
    )

    current_date = date.today()
    current_month_start = first_day_of_month(start_date)

    total_received = 0
    total_saved = 0
    total_deleted = 0

    while current_month_start <= end_date:
        month_end = last_day_of_month(current_month_start)

        if month_end > end_date:
            month_end = end_date

        is_current_month = (
            current_month_start.year == current_date.year
            and current_month_start.month == current_date.month
        )

        current_day = current_month_start

        while current_day <= month_end:
            if is_current_month:
                date_stock = current_day
                date_end_for_request = current_day
            else:
                date_stock = month_end
                date_end_for_request = month_end

            logger.info(
                "TurnoverRaw API month/day request: date_start=%s, date_stock=%s, date_end=%s",
                current_month_start,
                date_stock,
                date_end_for_request,
            )

            rows = fetch_fb_turnover_api_rows(
                date_start=current_month_start,
                date_stock=date_stock,
                date_end=date_end_for_request,
            )

            total_received += len(rows)

            objects = [
                normalize_turnover_record(
                    record,
                    fallback_date_start=current_month_start,
                )
                for record in rows
            ]

            objects = [
                obj
                for obj in objects
                if obj.date_stock is not None and obj.date_end is not None
            ]

            with transaction.atomic():
                logger.info("TurnoverRaw delete started: date_stock=%s", date_stock)

                deleted_count, _ = TurnoverRaw.objects.filter(
                    date_stock=date_stock,
                ).delete()

                total_deleted += deleted_count

                logger.info("TurnoverRaw deleted rows: %s", deleted_count)

                TurnoverRaw.objects.bulk_create(objects, batch_size=5000)

                total_saved += len(objects)

                logger.info(
                    "TurnoverRaw insert finished: date_stock=%s, rows=%s",
                    date_stock,
                    len(objects),
                )

            if not is_current_month:
                break

            current_day += timedelta(days=1)

        current_month_start = add_month(current_month_start)

    result = {
        "received": total_received,
        "saved": total_saved,
        "deleted": total_deleted,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "skipped": False,
    }

    logger.info("TurnoverRaw API load finished: %s", result)

    return result