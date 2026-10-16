import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import load_workbook

from datasets.models import TransportCost as LegacyTransportCost


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


def load_transport_cost_from_excel(file_obj, *, workspace=None) -> dict:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        return _load_workbook(workbook, workspace=workspace)
    finally:
        workbook.close()


def _load_workbook(workbook, *, workspace=None):
    TransportCost = workspace.model("TransportCost") if workspace is not None else LegacyTransportCost
    strict = workspace is not None and workspace.code == "select-market"
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
        if strict and not any(value is not None and str(value).strip() for value in row):
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
            if strict:
                raise ValueError(f"Invalid source data at row {row_index}")
            skipped += 1
            continue

        if strict and (not cost.is_finite() or cost < 0):
            raise ValueError(f"Invalid cost at row {row_index}")

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

    incoming_rows = [
        {
            "departure": departure,
            "arrival": arrival,
            "cost": cost,
        }
        for (departure, arrival), cost in rows_by_key.items()
    ]

    created = 0
    changed = 0
    unchanged = 0
    deactivated = 0

    with transaction.atomic():
        departures = {
            row["departure"]
            for row in incoming_rows
        }

        arrivals = {
            row["arrival"]
            for row in incoming_rows
        }

        active_objects = list(
            TransportCost.objects
            .select_for_update()
            .filter(
                departure__in=departures,
                arrival__in=arrivals,
                is_active=True,
            )
        )

        active_by_key = {
            (
                obj.departure.strip().casefold(),
                obj.arrival.strip().casefold(),
            ): obj
            for obj in active_objects
        }

        objects_to_create = []
        ids_to_deactivate = []

        for row in incoming_rows:
            key = (
                row["departure"].strip().casefold(),
                row["arrival"].strip().casefold(),
            )

            active_obj = active_by_key.get(key)

            if active_obj is None:
                objects_to_create.append(
                    TransportCost(
                        departure=row["departure"],
                        arrival=row["arrival"],
                        cost=row["cost"],
                        is_active=True,
                    )
                )

                created += 1
                continue

            if active_obj.cost == row["cost"]:
                unchanged += 1
                continue

            ids_to_deactivate.append(active_obj.pk)

            objects_to_create.append(
                TransportCost(
                    departure=row["departure"],
                    arrival=row["arrival"],
                    cost=row["cost"],
                    is_active=True,
                )
            )

            changed += 1

        if ids_to_deactivate:
            deactivated = (
                TransportCost.objects
                .filter(
                    pk__in=ids_to_deactivate,
                    is_active=True,
                )
                .update(
                    is_active=False,
                )
            )

        if objects_to_create:
            TransportCost.objects.bulk_create(
                objects_to_create,
                batch_size=1000,
            )

    result = {
        "received_unique": len(rows_by_key),
        "created": created,
        "changed": changed,
        "unchanged": unchanged,
        "deactivated": deactivated,
        "saved_new_versions": len(objects_to_create),
        "duplicates": duplicates,
        "skipped": skipped,
    }

    logger.info(
        "Transport cost loaded from Excel: %s",
        result,
    )

    return result