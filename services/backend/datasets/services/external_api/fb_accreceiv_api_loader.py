import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from datasets.models import AccreceivRaw
from datasets.services.external_api.fb_accreceiv_api_client import (
    fetch_fb_accreceiv_api_rows,
)


logger = logging.getLogger("external_api.fb_accreceiv")


def clean_str(value, default="-"):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


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


def get_accreceiv_load_period(end_date=None):
    end_date = end_date or date.today()

    max_date = AccreceivRaw.objects.aggregate(
        max_date=Max("date_start")
    )["max_date"]

    logger.info("AccreceivRaw current max date_start: %s", max_date)

    if max_date is None:
        start_date = date(2024, 1, 1)
    else:
        start_date = max_date - timedelta(days=70)

    return start_date, end_date


def normalize_accreceiv_record(record):
    return AccreceivRaw(
        date_start=clean_date(record.get("date_start")),
        date_end=clean_date(record.get("date_end")),

        partner=clean_str(record.get("partner")),
        contract_partner=clean_str(record.get("contract_partner")),
        manager_name=clean_str(record.get("manager_name")),

        mutual_instock=clean_decimal(record.get("mutual_instock")),
        mutual_comstock=clean_decimal(record.get("mutual_comstock")),
        mutual_spenstock=clean_decimal(record.get("mutual_spenstock")),
        mutual_finstock=clean_decimal(record.get("mutual_finstock")),

        initial_stock=clean_decimal(record.get("initial_stock")),
        coming_stock=clean_decimal(record.get("coming_stock")),
        spending_stock=clean_decimal(record.get("spending_stock")),
        final_stock=clean_decimal(record.get("final_stock")),
    )


def load_accreceiv_raw_from_api(start_date=None, end_date=None):
    logger.info("AccreceivRaw API load started")

    if start_date is None or end_date is None:
        start_date, end_date = get_accreceiv_load_period(end_date=end_date)

    if start_date > end_date:
        logger.info(
            "AccreceivRaw API load skipped: start_date=%s > end_date=%s",
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
        "AccreceivRaw API load period: start_date=%s, end_date=%s",
        start_date,
        end_date,
    )

    total_received = 0
    total_saved = 0
    total_deleted = 0

    current_date = start_date

    while current_date <= end_date:
        logger.info("AccreceivRaw API day started: %s", current_date)

        rows = fetch_fb_accreceiv_api_rows(
            date_start=current_date,
            date_end=current_date,
        )

        total_received += len(rows)

        objects = [
            normalize_accreceiv_record(record)
            for record in rows
        ]

        objects = [
            obj
            for obj in objects
            if obj.date_start is not None and obj.date_end is not None
        ]

        with transaction.atomic():
            logger.info("AccreceivRaw delete started: date_start=%s", current_date)

            deleted_count, _ = AccreceivRaw.objects.filter(
                date_start=current_date,
            ).delete()

            total_deleted += deleted_count

            logger.info("AccreceivRaw deleted rows: %s", deleted_count)

            AccreceivRaw.objects.bulk_create(objects, batch_size=5000)

            total_saved += len(objects)

            logger.info(
                "AccreceivRaw insert finished: date_start=%s, rows=%s",
                current_date,
                len(objects),
            )

        current_date += timedelta(days=1)

    result = {
        "received": total_received,
        "saved": total_saved,
        "deleted": total_deleted,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "skipped": False,
    }

    logger.info("AccreceivRaw API load finished: %s", result)

    return result