import logging

from openpyxl import load_workbook
from django.db import transaction
from django.utils import timezone

from datasets.models import (
    ParserProductClassification,
    BaseProductPrice,
    TaraProductPrice,
    PsProductPrice,
    TtProductPrice,
)


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



def enrich_classification_urls_and_images(product_keys):
    """
    Заполняет url и image в ParserProductClassification
    по данным соответствующих price-таблиц.

    Если для product_key существует несколько исторических записей,
    используется самая свежая.
    """

    product_keys = set(product_keys)

    if not product_keys:
        return 0

    values_by_product_key = {}

    price_models = (
        BaseProductPrice,
        TaraProductPrice,
        PsProductPrice,
        TtProductPrice,
    )

    for model in price_models:
        rows = (
            model.objects
            .filter(product_key__in=product_keys)
            .order_by("product_key", "-date_add", "-id")
            .values(
                "product_key",
                "url",
                "image",
            )
        )

        for row in rows:
            product_key = row["product_key"]

            # Нам нужна только самая свежая строка данного
            # product_key из соответствующей таблицы.
            if product_key in values_by_product_key:
                continue

            values_by_product_key[product_key] = {
                "url": clean_value(row.get("url")),
                "image": clean_value(row.get("image")),
            }

    classifications = list(
        ParserProductClassification.objects.filter(
            product_key__in=product_keys,
        )
    )

    objects_to_update = []

    for obj in classifications:
        values = values_by_product_key.get(obj.product_key)

        if not values:
            continue

        obj.url = values["url"]
        obj.image = values["image"]

        objects_to_update.append(obj)

    if objects_to_update:
        ParserProductClassification.objects.bulk_update(
            objects_to_update,
            fields=[
                "url",
                "image",
            ],
            batch_size=1000,
        )

    return len(objects_to_update)



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

        material = clean_value(row[4] if len(row) > 4 else None)
        color = clean_value(row[5] if len(row) > 5 else None)
        modification = clean_value(row[6] if len(row) > 6 else None)

        if not product_key:
            skipped += 1
            continue

        rows_by_product_key[product_key] = {
            "product_key": product_key,
            "category": category,
            "subcategory": subcategory,
            "subcategory_type": subcategory_type,

            "material": material,
            "color": color,
            "modification": modification,
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
                    material=row["material"],
                    color=row["color"],
                    modification=row["modification"],
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

        enriched = enrich_classification_urls_and_images(
            file_product_keys
        )

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
        "enriched": enriched,
        "skipped": skipped,
        "empty_file": False,
    }

    logger.info("Product classification loaded from Excel: %s", result)

    return result