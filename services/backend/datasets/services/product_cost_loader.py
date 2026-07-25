import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import load_workbook

from datasets.models import ProductCost


logger = logging.getLogger("datasets")


def clean_text(value, default=None):
    if value is None:
        return default

    value = str(value).strip()

    if not value:
        return default

    return value


def first_word(value):
    value = clean_text(value)

    if value is None:
        return None

    return value.split()[0]


def clean_int(value):
    if value is None:
        return None

    value = (
        str(value)
        .strip()
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
    )

    if not value:
        return None

    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def clean_decimal(value):
    if value is None:
        return None

    value = (
        str(value)
        .strip()
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
    )

    if not value:
        return None

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None


def clean_month(value):
    """
    Любую дату приводим к первому числу месяца.

    01.01.26 -> 2026-01-01
    15.01.26 -> 2026-01-01
    Excel datetime -> 2026-01-01
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return date(
            value.year,
            value.month,
            1,
        )

    if isinstance(value, date):
        return date(
            value.year,
            value.month,
            1,
        )

    value = str(value).strip()

    if not value:
        return None

    formats = (
        "%d.%m.%y",
        "%d.%m.%Y",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            parsed = datetime.strptime(
                value,
                fmt,
            ).date()

            return date(
                parsed.year,
                parsed.month,
                1,
            )

        except ValueError:
            continue

    return None


def load_product_cost_from_excel(file_obj) -> dict:
    workbook = load_workbook(
        file_obj,
        read_only=True,
        data_only=True,
    )

    worksheet = workbook.active

    # key:
    # (месяц, код номенклатуры, пункт отправления)
    #
    # value:
    # строка с максимальной себестоимостью.
    rows_by_key = {}

    skipped = 0
    duplicates = 0

    for row_index, row in enumerate(
        worksheet.iter_rows(values_only=True),
        start=1,
    ):
        if row_index == 1:
            continue

        month = clean_month(
            row[0] if len(row) > 0 else None
        )

        code = clean_int(
            row[1] if len(row) > 1 else None
        )

        name = clean_text(
            row[2] if len(row) > 2 else None
        )

        departure = first_word(
            row[3] if len(row) > 3 else None
        )

        cost = clean_decimal(
            row[4] if len(row) > 4 else None
        )

        if (
            month is None
            or code is None
            or not departure
            or cost is None
        ):
            skipped += 1
            continue

        key = (
            month,
            code,
            departure,
        )

        current = rows_by_key.get(key)

        if current is None:
            rows_by_key[key] = {
                "date": month,
                "code": code,
                "name": name,
                "departure": departure,
                "cost": cost,
            }

            continue

        duplicates += 1

        if cost > current["cost"]:
            rows_by_key[key] = {
                "date": month,
                "code": code,
                "name": name,
                "departure": departure,
                "cost": cost,
            }

    if not rows_by_key:
        raise ValueError(
            "Product cost Excel contains no valid rows. "
            "Existing data will not be deleted."
        )

    objects = [
        ProductCost(
            date=row["date"],
            code=row["code"],
            name=row["name"],
            departure=row["departure"],
            cost=row["cost"],
        )
        for row in rows_by_key.values()
    ]

    with transaction.atomic():
        deleted_count, _ = ProductCost.objects.all().delete()

        ProductCost.objects.bulk_create(
            objects,
            batch_size=5000,
        )

    result = {
        "received_unique": len(rows_by_key),
        "saved": len(objects),
        "deleted": deleted_count,
        "duplicates": duplicates,
        "skipped": skipped,
    }

    logger.info(
        "Product cost loaded from Excel: %s",
        result,
    )

    return result