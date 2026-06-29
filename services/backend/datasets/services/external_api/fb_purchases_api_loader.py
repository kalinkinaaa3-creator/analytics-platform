import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from datasets.models import FBPurchasesRaw
from datasets.services.external_api.fb_purchases_api_client import (
    fetch_fb_purchases_api_rows,
)


logger = logging.getLogger("external_api.fb_purchases")


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

    try:
        dt_utc = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        moscow_tz = timezone(timedelta(hours=3))
        dt_moscow = dt_utc.astimezone(moscow_tz)
        return dt_moscow.date()
    except Exception:
        pass

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def clean_date_draft(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None
    

def get_fb_purchases_load_period(end_date=None):
    end_date = end_date or date.today()

    max_date = FBPurchasesRaw.objects.aggregate(
        max_date=Max("date_1C")
    )["max_date"]

    logger.info("FBPurchasesRaw current max date: %s", max_date)

    if max_date is None:
        start_date = date(2024, 1, 1)
    else:
        start_date = max_date - timedelta(days=180)

    return start_date, end_date


def normalize_fb_purchases_raw_record(record):
    raw_date = record.get("date_1C")
    row_date = clean_date(raw_date)
    draft_date = clean_date_draft(raw_date)

    return FBPurchasesRaw(
        date_1C=row_date,

        quantity_1C_110=clean_decimal(record.get("quantity_1C_110")),
        revenue_1C_110=clean_decimal(record.get("revenue_1C_110")),
        VAT_1C_110=clean_decimal(record.get("VAT_1C_110")),

        quantity_1C_112=clean_decimal(record.get("quantity_1C_112")),
        revenue_1C_112=clean_decimal(record.get("revenue_1C_112")),
        VAT_1C_112=clean_decimal(record.get("VAT_1C_112")),

        quantity_1C_100753=clean_decimal(record.get("quantity_1C_100753")),
        revenue_1C_100753=clean_decimal(record.get("revenue_1C_100753")),
        VAT_1C_100753=clean_decimal(record.get("VAT_1C_100753")),

        date_draft=draft_date,
        party_status=clean_str(record.get("party_status")),
        partner=clean_str(record.get("partner")),
        nomenclature=clean_str(record.get("nomenclature")),
    )


def load_fb_purchases_raw_from_api(start_date=None, end_date=None):
    logger.info("FBPurchasesRaw API load started")

    if start_date is None or end_date is None:
        start_date, end_date = get_fb_purchases_load_period(end_date=end_date)

    if start_date > end_date:
        logger.info(
            "FBPurchasesRaw API load skipped: start_date=%s > end_date=%s",
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
        "FBPurchasesRaw API load period: start_date=%s, end_date=%s",
        start_date,
        end_date,
    )

    rows = fetch_fb_purchases_api_rows(
        start_date=start_date,
        end_date=end_date,
    )

    logger.info("FBPurchasesRaw API rows received: %s", len(rows))

    objects = [
        normalize_fb_purchases_raw_record(record)
        for record in rows
    ]

    objects = [
        obj
        for obj in objects
        if obj.date_1C is not None
    ]

    logger.info("FBPurchasesRaw normalize finished: objects=%s", len(objects))

    with transaction.atomic():
        logger.info("FBPurchasesRaw PostgreSQL delete started: date_1C >= %s", start_date)

        deleted_count, _ = FBPurchasesRaw.objects.filter(
            date_1C__gte=start_date,
        ).delete()

        logger.info("FBPurchasesRaw PostgreSQL deleted rows: %s", deleted_count)

        FBPurchasesRaw.objects.bulk_create(objects, batch_size=5000)

        logger.info("FBPurchasesRaw PostgreSQL insert finished: rows=%s", len(objects))

    result = {
        "received": len(rows),
        "saved": len(objects),
        "deleted": deleted_count,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "skipped": False,
    }

    logger.info("FBPurchasesRaw API load finished: %s", result)

    return result