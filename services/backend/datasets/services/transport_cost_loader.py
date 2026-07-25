import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import load_workbook

from datasets.models import TransportCost


logger = logging.getLogger("datasets")


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def first_word(value):
    """
    Берем всё до первого пробела.

    'Нижнекамск г.'     -> 'Нижнекамск'
    'Санкт-Петербург'  -> 'Санкт-Петербург'
    'Азов'              -> 'Азов'
    """
    value = clean_text(value)

    if value is None:
        return None

    return value.split()[0]


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


def load_transport_cost_from_excel(file_obj) -> dict:
    workbook = load_workbook(
        file_obj,
        read_only=True,
        data_only=True,
    )

    worksheet = workbook.active

    # key = (departure, arrival)
    # value = максимальная стоимость
    rows_by_key = {}

    skipped = 0
    duplicates = 0

    for row_index, row in enumerate(
        worksheet.iter_rows(values_only=True),
        start=1,
    ):
        if row_index == 1:
            continue

        departure = first_word(
            row[0] if len(row) > 0 else None
        )

        arrival = first_word(
            row[1] if len(row) > 1 else None
        )

        cost = clean_decimal(
            row[2] if len(row) > 2 else None
        )

        if not departure or not arrival or cost is None:
            skipped += 1
            continue

        key = (
            departure,
            arrival,
        )

        existing_cost = rows_by_key.get(key)

        if existing_cost is None:
            rows_by_key[key] = cost
            continue

        duplicates += 1

        # При дубле сохраняем максимальную стоимость.
        if cost > existing_cost:
            rows_by_key[key] = cost

    if not rows_by_key:
        raise ValueError(
            "Transport cost Excel contains no valid rows. "
            "Existing data will not be deleted."
        )

    objects = [
        TransportCost(
            departure=departure,
            arrival=arrival,
            cost=cost,
        )
        for (departure, arrival), cost in rows_by_key.items()
    ]

    with transaction.atomic():
        deleted_count, _ = TransportCost.objects.all().delete()

        TransportCost.objects.bulk_create(
            objects,
            batch_size=1000,
        )

    result = {
        "received_unique": len(rows_by_key),
        "saved": len(objects),
        "deleted": deleted_count,
        "duplicates": duplicates,
        "skipped": skipped,
    }

    logger.info(
        "Transport cost loaded from Excel: %s",
        result,
    )

    return result