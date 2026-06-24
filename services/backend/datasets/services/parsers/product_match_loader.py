import logging

from openpyxl import load_workbook
from django.db import transaction
from django.utils import timezone

from datasets.models import ParserProductMatch


logger = logging.getLogger("parser_product_match.datasets")


def clean_int(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_product_matches_from_excel(file_obj) -> dict:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    worksheet = workbook.active

    file_pairs = set()
    skipped = 0

    for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        if row_index == 1:
            continue

        product_key_base = clean_int(row[0] if len(row) > 0 else None)
        product_key_competitor = clean_int(row[1] if len(row) > 1 else None)

        if not product_key_base or not product_key_competitor:
            skipped += 1
            continue

        file_pairs.add((product_key_base, product_key_competitor))

    if not file_pairs:
        result = {
            "created": 0,
            "reactivated": 0,
            "unchanged": 0,
            "inactivated": 0,
            "skipped": skipped,
            "empty_file": True,
        }
        logger.info("Product match upload skipped: empty file/result=%s", result)
        return result

    now = timezone.now()

    created = 0
    reactivated = 0
    unchanged = 0
    inactivated = 0

    with transaction.atomic():
        existing = {
            (obj.product_key_base, obj.product_key_competitor): obj
            for obj in ParserProductMatch.objects.all()
        }

        for pair in file_pairs:
            obj = existing.get(pair)

            if obj is None:
                ParserProductMatch.objects.create(
                    product_key_base=pair[0],
                    product_key_competitor=pair[1],
                    status=ParserProductMatch.STATUS_ACTIVE,
                    date_update=now,
                )
                created += 1
                continue

            if obj.status == ParserProductMatch.STATUS_INACTIVE:
                obj.status = ParserProductMatch.STATUS_ACTIVE
                obj.date_update = now
                obj.save(update_fields=["status", "date_update"])
                reactivated += 1
            else:
                unchanged += 1

        inactive_qs = ParserProductMatch.objects.exclude(
            product_key_base__in=[pair[0] for pair in file_pairs],
        )

        # Нельзя корректно сравнить пару через два отдельных __in,
        # поэтому деактивируем через перебор существующих.
        for pair, obj in existing.items():
            if pair in file_pairs:
                continue

            if obj.status == ParserProductMatch.STATUS_INACTIVE:
                continue

            obj.status = ParserProductMatch.STATUS_INACTIVE
            obj.date_update = now
            obj.save(update_fields=["status", "date_update"])
            inactivated += 1

    result = {
        "created": created,
        "reactivated": reactivated,
        "unchanged": unchanged,
        "inactivated": inactivated,
        "skipped": skipped,
        "empty_file": False,
    }

    logger.info("Product matches loaded from Excel: %s", result)

    return result