import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from datasets.models import AccreceivRaw


logger = logging.getLogger("external_api.fb_accreceiv")


CSV_COLUMNS = [
    "date_start",
    "date_end",
    "partner",
    "contract_partner",
    "manager_name",
    "mutual_instock",
    "mutual_comstock",
    "mutual_spenstock",
    "mutual_finstock",
    "initial_stock",
    "coming_stock",
    "spending_stock",
    "final_stock",
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
    return AccreceivRaw(
        date_start=clean_date(row.get("date_start")),
        date_end=clean_date(row.get("date_end")),

        partner=clean_str(row.get("partner")),
        contract_partner=clean_str(row.get("contract_partner")),
        manager_name=clean_str(row.get("manager_name")),

        mutual_instock=clean_decimal(row.get("mutual_instock")),
        mutual_comstock=clean_decimal(row.get("mutual_comstock")),
        mutual_spenstock=clean_decimal(row.get("mutual_spenstock")),
        mutual_finstock=clean_decimal(row.get("mutual_finstock")),

        initial_stock=clean_decimal(row.get("initial_stock")),
        coming_stock=clean_decimal(row.get("coming_stock")),
        spending_stock=clean_decimal(row.get("spending_stock")),
        final_stock=clean_decimal(row.get("final_stock")),
    )


def load_accreceiv_raw_from_csv(
    csv_path: str,
    truncate_source: bool = True,
):
    logger.info("FBAccreceiv CSV load started: %s", csv_path)

    objects = []

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

        received = 0

        for row in reader:
            received += 1

            obj = normalize_row(row)

            if obj.date_start is None or obj.date_end is None:
                continue

            objects.append(obj)

    logger.info("FBAccreceiv CSV normalized rows: %s", len(objects))

    deleted_count = 0

    if truncate_source:
        logger.info("FBAccreceivRaw truncate started")

        deleted_count, _ = AccreceivRaw.objects.all().delete()

        logger.info("FBAccreceivRaw deleted rows: %s", deleted_count)

    batch_size = 5000
    saved = 0

    for index in range(0, len(objects), batch_size):
        batch = objects[index:index + batch_size]

        with transaction.atomic():
            AccreceivRaw.objects.bulk_create(batch, batch_size=batch_size)

        saved += len(batch)

        logger.info(
            "FBAccreceivRaw insert progress: %s/%s",
            saved,
            len(objects),
        )

    logger.info("FBAccreceivRaw insert finished: rows=%s", saved)

    return {
        "received": received,
        "saved": len(objects),
        "deleted": deleted_count,
        "csv_path": csv_path,
        "truncate_source": truncate_source,
    }