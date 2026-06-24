import logging

from openpyxl import load_workbook
from django.db import transaction
from django.utils import timezone

from datasets.models import ParserProductClassification


logger = logging.getLogger("datasets")


def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def clean_int(value):
    value = clean_value(value)

    if value is None:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_product_classification_from_excel(file_obj) -> dict:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    worksheet = workbook.active

    rows_by_product_key = {}
    skipped = 0

    for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        if row_index == 1:
            continue

        product_key = clean_int(row[0] if len(row) > 0 else None)
        category = clean_value(row[1] if len(row) > 1 else None)
        subcategory = clean_value(row[2] if len(row) > 2 else None)
        subcategory_type = clean_value(row[3] if len(row) > 3 else None)

        if not product_key:
            skipped += 1
            continue

        rows_by_product_key[product_key] = {
            "product_key": product_key,
            "category": category,
            "subcategory": subcategory,
            "subcategory_type": subcategory_type,
        }

    if not rows_by_product_key:
        result = {
            "created": 0,
            "replaced": 0,
            "inactivated": 0,
            "skipped": skipped,
            "empty_file": True,
        }

        logger.info("Product classification upload skipped: %s", result)

        return result

    now = timezone.now()

    created = 0
    replaced_count = 0
    inactivated = 0

    file_product_keys = set(rows_by_product_key.keys())

    with transaction.atomic():
        existing_product_keys = set(
            ParserProductClassification.objects.values_list(
                "product_key",
                flat=True,
            )
        )

        keys_to_replace = existing_product_keys & file_product_keys
        keys_to_create = file_product_keys - existing_product_keys
        keys_to_inactivate = existing_product_keys - file_product_keys

        if keys_to_replace:
            ParserProductClassification.objects.filter(
                product_key__in=keys_to_replace,
            ).delete()

            replaced_count = len(keys_to_replace)

        objects_to_create = []

        for product_key in sorted(keys_to_create | keys_to_replace):
            row = rows_by_product_key[product_key]

            objects_to_create.append(
                ParserProductClassification(
                    product_key=row["product_key"],
                    category=row["category"],
                    subcategory=row["subcategory"],
                    subcategory_type=row["subcategory_type"],
                    status=ParserProductClassification.STATUS_ACTIVE,
                    date_update=now,
                )
            )

        if objects_to_create:
            ParserProductClassification.objects.bulk_create(
                objects_to_create,
                batch_size=1000,
            )

        created = len(keys_to_create)

        if keys_to_inactivate:
            inactivated = ParserProductClassification.objects.filter(
                product_key__in=keys_to_inactivate,
            ).exclude(
                status=ParserProductClassification.STATUS_INACTIVE,
            ).update(
                status=ParserProductClassification.STATUS_INACTIVE,
                date_update=now,
            )

    result = {
        "created": created,
        "replaced": replaced_count,
        "inactivated": inactivated,
        "skipped": skipped,
        "empty_file": False,
    }

    logger.info("Product classification loaded from Excel: %s", result)

    return result