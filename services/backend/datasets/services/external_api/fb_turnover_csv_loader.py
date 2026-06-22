import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from datasets.models import TurnoverRaw


logger = logging.getLogger("external_api.fb_turnover")


CSV_COLUMNS = [
    "date_stock",
    "date_start",
    "date_end",
    "warehouse_group",
    "warehouse",
    "nomenclature",
    "quantity",
    "price",
    "amount_day",
    "middle_stock",
    "middle_rubstock",
]


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

    value = (
        str(value)
        .strip()
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
        "%Y%m%d",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            if fmt == "%Y%m%d":
                return datetime.strptime(value[:8], fmt).date()

            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    return None


def normalize_row(row):
    return TurnoverRaw(
        date_stock=clean_date(row.get("date_stock")),
        date_start=clean_date(row.get("date_start")),
        date_end=clean_date(row.get("date_end")),

        warehouse_group=clean_str(row.get("warehouse_group")),
        warehouse=clean_str(row.get("warehouse")),
        nomenclature=clean_str(row.get("nomenclature")),

        quantity=clean_str(row.get("quantity")),
        price=clean_decimal(row.get("price")),
        amount_day=clean_int(row.get("amount_day")),

        middle_stock=clean_decimal(row.get("middle_stock")),
        middle_rubstock=clean_decimal(row.get("middle_rubstock")),
    )


def insert_batch(batch, saved, total_valid_hint=None):
    if not batch:
        return saved

    with transaction.atomic():
        TurnoverRaw.objects.bulk_create(batch, batch_size=len(batch))

    saved += len(batch)

    if total_valid_hint:
        logger.info(
            "FBTurnoverRaw insert progress: %s/%s",
            saved,
            total_valid_hint,
        )
    else:
        logger.info(
            "FBTurnoverRaw insert progress: %s",
            saved,
        )

    return saved


def load_turnover_raw_from_csv(
    csv_path: str,
    truncate_source: bool = True,
    batch_size: int = 10000,
):
    logger.info("FBTurnover CSV load started: %s", csv_path)

    deleted_count = 0

    if truncate_source:
        logger.info("FBTurnoverRaw truncate started")

        deleted_count, _ = TurnoverRaw.objects.all().delete()

        logger.info("FBTurnoverRaw deleted rows: %s", deleted_count)

    received = 0
    skipped = 0
    saved = 0
    batch = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
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

        logger.info(
            "FBTurnover CSV reader initialized: delimiter=%s, columns=%s",
            delimiter,
            reader.fieldnames,
        )

        for row in reader:
            received += 1

            obj = normalize_row(row)

            if (
                obj.date_stock is None
                or obj.date_start is None
                or obj.date_end is None
            ):
                skipped += 1
                continue

            batch.append(obj)

            if len(batch) >= batch_size:
                saved = insert_batch(batch=batch, saved=saved)
                batch = []

        if batch:
            saved = insert_batch(batch=batch, saved=saved)

    logger.info(
        "FBTurnover CSV load finished: received=%s, saved=%s, skipped=%s",
        received,
        saved,
        skipped,
    )

    return {
        "received": received,
        "saved": saved,
        "skipped": skipped,
        "deleted": deleted_count,
        "csv_path": csv_path,
        "truncate_source": truncate_source,
        "batch_size": batch_size,
    }


'''
from analytics.services.fb_turnover_csv_pipeline import run_fb_turnover_csv_pipeline

run_fb_turnover_csv_pipeline(
    csv_path="/app/media/datasets/fb_turnover.csv",
    truncate_source=True,
)
'''