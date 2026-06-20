import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from datasets.models import FBPurchasesRaw


logger = logging.getLogger("external_api.fb_purchases")


CSV_COLUMNS = [
    "date_1C",

    "quantity_1C_110",
    "revenue_1C_110",
    "VAT_1C_110",

    "quantity_1C_112",
    "revenue_1C_112",
    "VAT_1C_112",

    "quantity_1C_100753",
    "revenue_1C_100753",
    "VAT_1C_100753",

    "date_draft",

    "party_status",
    "partner",
    "nomenclature",
]


def clean_str(value, default="-"):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def clean_decimal(value, default=Decimal("0")):
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
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    return None


def normalize_row(row):
    return FBPurchasesRaw(
        date_1C=clean_date(row.get("date_1C")),

        quantity_1C_110=clean_decimal(row.get("quantity_1C_110")),
        revenue_1C_110=clean_decimal(row.get("revenue_1C_110")),
        VAT_1C_110=clean_decimal(row.get("VAT_1C_110")),

        quantity_1C_112=clean_decimal(row.get("quantity_1C_112")),
        revenue_1C_112=clean_decimal(row.get("revenue_1C_112")),
        VAT_1C_112=clean_decimal(row.get("VAT_1C_112")),

        quantity_1C_100753=clean_decimal(row.get("quantity_1C_100753")),
        revenue_1C_100753=clean_decimal(row.get("revenue_1C_100753")),
        VAT_1C_100753=clean_decimal(row.get("VAT_1C_100753")),

        date_draft=clean_date(row.get("date_draft")),

        party_status=clean_str(row.get("party_status")),
        partner=clean_str(row.get("partner")),
        nomenclature=clean_str(row.get("nomenclature")),
    )


def load_fb_purchases_raw_from_csv(file_path: str, truncate: bool = True):
    logger.info("FBPurchases CSV load started: %s", file_path)

    rows = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)

        delimiter = ";"
        if "," in sample and ";" not in sample:
            delimiter = ","

        reader = csv.DictReader(file, delimiter=delimiter)

        missing_columns = [
            column
            for column in CSV_COLUMNS
            if column not in (reader.fieldnames or [])
        ]

        if missing_columns:
            raise ValueError(
                f"CSV missing columns: {', '.join(missing_columns)}"
            )

        for row in reader:
            obj = normalize_row(row)

            if obj.date_1C is None or obj.date_draft is None:
                continue

            rows.append(obj)

    logger.info("FBPurchases CSV normalized rows: %s", len(rows))

    with transaction.atomic():
        deleted_count = 0

        if truncate:
            logger.info("FBPurchasesRaw truncate started")

            deleted_count, _ = FBPurchasesRaw.objects.all().delete()

            logger.info("FBPurchasesRaw deleted rows: %s", deleted_count)

        FBPurchasesRaw.objects.bulk_create(rows, batch_size=5000)

        logger.info("FBPurchasesRaw insert finished: rows=%s", len(rows))

    return {
        "received": len(rows),
        "saved": len(rows),
        "deleted": deleted_count,
        "file_path": file_path,
        "truncate": truncate,
    }