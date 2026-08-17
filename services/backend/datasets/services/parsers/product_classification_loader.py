import logging

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from datasets.models import (
    BaseProductPrice,
    ParserProductClassification,
    PsProductPrice,
    TaraProductPrice,
    TtProductPrice,
)


logger = logging.getLogger("datasets")


# ============================================================
# CLEANING HELPERS
# ============================================================


def clean_value(value):
    """
    Приводит значение к очищенной строке.

    None        -> None
    ""          -> None
    "  Товар "  -> "Товар"
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def clean_int(value):
    """
    Приводит числовое значение Excel к int.

    Поддерживает:

        123
        123.0
        "123"
        "123.0"

    Некорректное значение возвращает как None.
    """

    value = clean_value(value)

    if value is None:
        return None

    try:
        return int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def clean_item_type(value):
    """
    Нормализует тип товара.

    Допустимые итоговые значения:

        product
        component

    Регистр и внешние пробелы игнорируются.

    Примеры:

        "PRODUCT"       -> "product"
        " Component "   -> "component"
        "товар"         -> None
        None            -> None
    """

    value = clean_value(value)

    if value is None:
        return None

    value = value.casefold()

    allowed_values = {
        ParserProductClassification.ITEM_TYPE_PRODUCT,
        ParserProductClassification.ITEM_TYPE_COMPONENT,
    }

    if value not in allowed_values:
        return None

    return value


# ============================================================
# URL AND IMAGE ENRICHMENT
# ============================================================


def enrich_classification_urls_and_images(
    product_keys,
):
    """
    Заполняет url и image в ParserProductClassification
    по данным соответствующих price-таблиц.

    Таблицы:

        BaseProductPrice
        TaraProductPrice
        PsProductPrice
        TtProductPrice

    product_key считается уникальным между источниками.

    Если для product_key существует несколько исторических
    записей, используется самая свежая строка:

        date_add DESC
        id DESC

    ВАЖНО:

    Эта функция отвечает только за url и image.
    Правило выбора расчетной final_price здесь не применяется.
    """

    product_keys = set(
        product_keys
    )

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
            .filter(
                product_key__in=product_keys
            )
            .order_by(
                "product_key",
                "-date_add",
                "-id",
            )
            .values(
                "product_key",
                "url",
                "image",
            )
        )

        for row in rows:
            product_key = row[
                "product_key"
            ]

            values = values_by_product_key.setdefault(
                product_key,
                {"url": None, "image": None},
            )
            if values["url"] is None:
                values["url"] = clean_value(row.get("url"))
            if values["image"] is None:
                values["image"] = clean_value(row.get("image"))

    classifications = list(
        ParserProductClassification.objects.filter(
            product_key__in=product_keys,
        )
    )

    objects_to_update = []

    for obj in classifications:
        values = (
            values_by_product_key.get(
                obj.product_key
            )
        )

        if not values:
            continue

        obj.url = values["url"] or obj.url
        obj.image = values["image"] or obj.image

        objects_to_update.append(
            obj
        )

    if objects_to_update:
        ParserProductClassification.objects.bulk_update(
            objects_to_update,
            fields=[
                "url",
                "image",
            ],
            batch_size=1000,
        )

    return len(
        objects_to_update
    )


# ============================================================
# MAIN EXCEL LOADER
# ============================================================


def load_product_classification_from_excel(
    file_obj,
) -> dict:
    """
    Загружает классификацию товаров из Excel.

    Ожидаемый порядок столбцов:

        0. product_key
        1. category
        2. subcategory
        3. subcategory_type
        4. material
        5. color
        6. modification
        7. item_type

    Допустимые item_type:

        product
        component

    Правила загрузки:

    1. Строка без корректного product_key пропускается.

    2. Строка без item_type или с некорректным item_type
       пропускается.

    3. Если product_key встречается в файле несколько раз,
       используется последняя корректная строка.

    4. Существующие строки по product_key из файла
       удаляются и создаются заново.

    5. Существующие строки, которых нет в новом файле,
       переводятся в status=inactive.

    6. После загрузки url и image обогащаются
       из соответствующих price-таблиц.

    ВАЖНО:

    Если в файле нет ни одной корректной строки,
    существующие данные не удаляются и не деактивируются.
    """

    workbook = load_workbook(
        file_obj,
        read_only=True,
        data_only=True,
    )

    worksheet = workbook.active

    rows_by_product_key = {}

    skipped = 0
    invalid_product_key = 0
    invalid_item_type = 0
    duplicates = 0

    for row_index, row in enumerate(
        worksheet.iter_rows(
            values_only=True
        ),
        start=1,
    ):
        # ----------------------------------------------------
        # Первая строка — заголовки
        # ----------------------------------------------------

        if row_index == 1:
            continue

        # ----------------------------------------------------
        # Читаем данные строки
        # ----------------------------------------------------

        product_key = clean_int(
            row[0]
            if len(row) > 0
            else None
        )

        category = clean_value(
            row[1]
            if len(row) > 1
            else None
        )

        subcategory = clean_value(
            row[2]
            if len(row) > 2
            else None
        )

        subcategory_type = clean_value(
            row[3]
            if len(row) > 3
            else None
        )

        material = clean_value(
            row[4]
            if len(row) > 4
            else None
        )

        color = clean_value(
            row[5]
            if len(row) > 5
            else None
        )

        modification = clean_value(
            row[6]
            if len(row) > 6
            else None
        )

        item_type = clean_item_type(
            row[7]
            if len(row) > 7
            else None
        )

        # ----------------------------------------------------
        # Проверка product_key
        # ----------------------------------------------------

        if not product_key:
            skipped += 1
            invalid_product_key += 1

            logger.warning(
                "Product classification row skipped: "
                "row=%s, invalid product_key=%r",
                row_index,
                (
                    row[0]
                    if len(row) > 0
                    else None
                ),
            )

            continue

        # ----------------------------------------------------
        # Проверка item_type
        #
        # Допустимы только:
        # product
        # component
        # ----------------------------------------------------

        if item_type is None:
            skipped += 1
            invalid_item_type += 1

            logger.warning(
                "Product classification row skipped: "
                "row=%s, product_key=%s, "
                "invalid item_type=%r. "
                "Expected product or component.",
                row_index,
                product_key,
                (
                    row[7]
                    if len(row) > 7
                    else None
                ),
            )

            continue

        # ----------------------------------------------------
        # Контроль дубликатов внутри файла
        #
        # Последняя корректная строка по product_key
        # заменяет предыдущую.
        # ----------------------------------------------------

        if product_key in rows_by_product_key:
            duplicates += 1

        rows_by_product_key[
            product_key
        ] = {
            "product_key": product_key,
            "category": category,
            "subcategory": subcategory,
            "subcategory_type": (
                subcategory_type
            ),
            "material": material,
            "color": color,
            "modification": modification,
            "item_type": item_type,
        }

    # ========================================================
    # ЗАЩИТА ОТ ПУСТОГО ИЛИ ПОЛНОСТЬЮ НЕКОРРЕКТНОГО ФАЙЛА
    # ========================================================

    if not rows_by_product_key:
        result = {
            "created": 0,
            "replaced": 0,
            "inactivated": 0,
            "enriched": 0,
            "skipped": skipped,
            "invalid_product_key": (
                invalid_product_key
            ),
            "invalid_item_type": (
                invalid_item_type
            ),
            "duplicates": duplicates,
            "empty_file": True,
        }

        logger.info(
            "Product classification upload skipped: %s",
            result,
        )

        return result

    now = timezone.now()

    created = 0
    updated = 0
    converted_to_manual = 0
    reactivated = 0
    inactivated = 0
    enriched = 0

    file_product_keys = set(
        rows_by_product_key
    )

    with transaction.atomic():
        existing_objects = {
            obj.product_key: obj
            for obj in (
                ParserProductClassification
                .objects
                .select_for_update()
                .filter(
                    product_key__in=(
                        file_product_keys
                    ),
                )
            )
        }

        objects_to_create = []
        objects_to_update = []

        update_fields = [
            "category",
            "subcategory",
            "subcategory_type",
            "material",
            "color",
            "modification",
            "item_type",
            "status",
            "match_type",
            "date_update",
        ]

        for product_key in sorted(
            file_product_keys
        ):
            row = rows_by_product_key[
                product_key
            ]

            existing = (
                existing_objects.get(
                    product_key
                )
            )

            if existing is None:
                objects_to_create.append(
                    ParserProductClassification(
                        product_key=product_key,
                        category=row["category"],
                        subcategory=(
                            row["subcategory"]
                        ),
                        subcategory_type=(
                            row[
                                "subcategory_type"
                            ]
                        ),
                        material=row["material"],
                        color=row["color"],
                        modification=(
                            row["modification"]
                        ),
                        item_type=(
                            row["item_type"]
                        ),
                        status=(
                            ParserProductClassification
                            .STATUS_ACTIVE
                        ),
                        match_type=(
                            ParserProductClassification
                            .MATCH_TYPE_MANUAL
                        ),
                        date_update=now,
                    )
                )

                created += 1
                continue

            if (
                existing.match_type
                == ParserProductClassification
                .MATCH_TYPE_AUTO
            ):
                converted_to_manual += 1

            if (
                existing.status
                == ParserProductClassification
                .STATUS_INACTIVE
            ):
                reactivated += 1

            existing.category = (
                row["category"]
            )

            existing.subcategory = (
                row["subcategory"]
            )

            existing.subcategory_type = (
                row["subcategory_type"]
            )

            existing.material = (
                row["material"]
            )

            existing.color = row["color"]

            existing.modification = (
                row["modification"]
            )

            existing.item_type = (
                row["item_type"]
            )

            existing.status = (
                ParserProductClassification
                .STATUS_ACTIVE
            )

            existing.match_type = (
                ParserProductClassification
                .MATCH_TYPE_MANUAL
            )

            existing.date_update = now

            objects_to_update.append(
                existing
            )

            updated += 1

        if objects_to_create:
            (
                ParserProductClassification
                .objects
                .bulk_create(
                    objects_to_create,
                    batch_size=1000,
                )
            )

        if objects_to_update:
            (
                ParserProductClassification
                .objects
                .bulk_update(
                    objects_to_update,
                    fields=update_fields,
                    batch_size=1000,
                )
            )

        # Деактивируем только ручные классификации,
        # которые отсутствуют в новом полном Excel.
        #
        # Автоматические строки управляются
        # product_match_loader и здесь не затрагиваются.
        inactivated = (
            ParserProductClassification
            .objects
            .filter(
                match_type=(
                    ParserProductClassification
                    .MATCH_TYPE_MANUAL
                ),
                status=(
                    ParserProductClassification
                    .STATUS_ACTIVE
                ),
            )
            .exclude(
                product_key__in=(
                    file_product_keys
                ),
            )
            .update(
                status=(
                    ParserProductClassification
                    .STATUS_INACTIVE
                ),
                date_update=now,
            )
        )

        enriched = (
            enrich_classification_urls_and_images(
                file_product_keys
            )
        )

    result = {
        "created": created,
        "updated": updated,
        "converted_to_manual": (
            converted_to_manual
        ),
        "reactivated": reactivated,
        "inactivated": inactivated,
        "enriched": enriched,
        "skipped": skipped,
        "invalid_product_key": (
            invalid_product_key
        ),
        "invalid_item_type": (
            invalid_item_type
        ),
        "duplicates": duplicates,
        "empty_file": False,
    }

    logger.info(
        (
            "Product classification loaded "
            "from Excel: %s"
        ),
        result,
    )

    return result
