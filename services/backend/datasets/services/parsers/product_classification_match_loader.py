from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from datasets.models import (
    IPriceCompetitorSelectionOverride,
    ParserProductClassification,
    ParserProductMatch,
    ParserProductUrl,
)
from datasets.services.parsers.regional_product_groups import (
    build_competitor_url_groups,
    get_prefixes_by_source,
)
from datasets.services.parsers.product_image_sync import sync_iprice_product_images


REQUIRED_COLUMNS = (
    "product_key",
    "category",
    "subcategory",
    "subcategory_type",
    "color",
    "material",
    "modification",
    "article_number_analogs",
    "item_type",
)
WILDCARD_COLOR_LABEL = "цвет не установлен"
WILDCARD_COLOR_VALUES = {
    "-", "__any__", WILDCARD_COLOR_LABEL, "любой цвет (по запросу)",
}


class ProductClassificationMatchLoadError(ValueError):
    pass


def _clean(value):
    return "" if value is None else str(value).strip()


def _product_key(value):
    if isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _normalized_color(value):
    value = " ".join(_clean(value).casefold().replace("ё", "е").split())
    return "__any__" if value in WILDCARD_COLOR_VALUES else value


def _colors_match(left, right):
    left = _normalized_color(left)
    right = _normalized_color(right)
    return left == "__any__" or right == "__any__" or left == right


def _read_rows(file_obj):
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        try:
            headers = tuple(_clean(value) for value in next(rows))
        except StopIteration as exc:
            raise ProductClassificationMatchLoadError("Файл классификации пуст") from exc
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise ProductClassificationMatchLoadError(
                "Отсутствуют обязательные столбцы: " + ", ".join(missing)
            )
        indexes = {column: headers.index(column) for column in REQUIRED_COLUMNS}
        result = []
        errors = []
        for number, values in enumerate(rows, start=2):
            if not any(value not in (None, "") for value in values):
                continue
            row = {
                column: values[index] if index < len(values) else None
                for column, index in indexes.items()
            }
            row["row_number"] = number
            row["product_key"] = _product_key(row["product_key"])
            for column in REQUIRED_COLUMNS[1:]:
                row[column] = _clean(row[column])
            row["item_type"] = row["item_type"].casefold()
            reasons = []
            if row["product_key"] is None:
                reasons.append("Некорректный product_key")
            if row["item_type"] not in {
                ParserProductClassification.ITEM_TYPE_PRODUCT,
                ParserProductClassification.ITEM_TYPE_COMPONENT,
            }:
                reasons.append("Некорректный item_type")
            if not row["article_number_analogs"]:
                reasons.append("Не заполнен article_number_analogs")
            if reasons:
                errors.append(f"Строка {number}: " + "; ".join(reasons))
            else:
                result.append(row)
        if errors:
            raise ProductClassificationMatchLoadError("\n".join(errors[:100]))
        if not result:
            raise ProductClassificationMatchLoadError("Нет строк для загрузки")
        return result
    finally:
        workbook.close()


def _prepare(file_obj):
    rows = _read_rows(file_obj)
    requested_keys = {row["product_key"] for row in rows}
    urls = {
        row.id: row
        for row in ParserProductUrl.objects.filter(
            id__in=requested_keys,
            status=ParserProductUrl.STATUS_ACTIVE,
        ).only("id", "source", "url", "prefix")
    }
    regional_groups, group_by_product = build_competitor_url_groups(
        prefixes_by_source=get_prefixes_by_source(),
    )
    classifications = {}
    groups = defaultdict(lambda: {"base": defaultdict(set), "competitor": defaultdict(set)})
    skipped = []

    for row in rows:
        url = urls.get(row["product_key"])
        if url is None:
            skipped.append({"row": row["row_number"], "product_key": row["product_key"]})
            continue
        resolved = {row["product_key"]}
        if url.source in {"tara", "ps"}:
            resolved.update(regional_groups.get(group_by_product.get(url.id), ()))
        values = {
            "category": row["category"],
            "subcategory": row["subcategory"],
            "subcategory_type": row["subcategory_type"],
            "color": (
                WILDCARD_COLOR_LABEL
                if _normalized_color(row["color"]) == "__any__"
                else row["color"]
            ),
            "material": row["material"],
            "modification": row["modification"],
            "article_number_analogs": row["article_number_analogs"],
            "item_type": row["item_type"],
        }
        group_key = (
            row["article_number_analogs"].casefold(),
            row["item_type"], row["category"].casefold(),
            row["subcategory"].casefold(), row["subcategory_type"].casefold(),
        )
        side = "base" if url.source == "base" else "competitor"
        for product_key in resolved:
            previous = classifications.get(product_key)
            if previous is not None and previous != values:
                raise ProductClassificationMatchLoadError(
                    f"product_key={product_key} получил разные классификации"
                )
            classifications[product_key] = values
            groups[group_key][side][row["color"]].add(product_key)

    pairs = set()
    for item in groups.values():
        for base_color, base_keys in item["base"].items():
            for competitor_color, competitor_keys in item["competitor"].items():
                if _colors_match(base_color, competitor_color):
                    pairs.update(
                        (base_key, competitor_key)
                        for base_key in base_keys for competitor_key in competitor_keys
                    )
    return classifications, pairs, skipped, len(rows)


def load_product_classification_matches(file_obj, *, filename=""):
    classifications, automatic_pairs, skipped, input_rows = _prepare(file_obj)
    now = timezone.now()
    excluded_pairs = set(
        IPriceCompetitorSelectionOverride.objects.filter(
            selection_mode=IPriceCompetitorSelectionOverride.MODE_EXCLUDE,
        ).values_list("product_key_base", "product_key_competitor")
    )
    active_automatic_pairs = automatic_pairs - excluded_pairs
    manual_pairs = set(
        ParserProductMatch.objects.filter(
            match_type=ParserProductMatch.MATCH_TYPE_MANUAL,
            status=ParserProductMatch.STATUS_ACTIVE,
        ).values_list("product_key_base", "product_key_competitor")
    )
    active_automatic_pairs -= manual_pairs
    preserved_manual_keys = {
        product_key
        for pair in manual_pairs
        for product_key in pair
    }
    preserved_manual_keys.update(
        IPriceCompetitorSelectionOverride.objects.filter(
            selection_mode=IPriceCompetitorSelectionOverride.MODE_INCLUDE,
        ).values_list("product_key_competitor", flat=True)
    )
    product_keys = set(classifications)
    url_by_key = dict(
        ParserProductUrl.objects.filter(id__in=product_keys).values_list("id", "url")
    )

    with transaction.atomic():
        ParserProductClassification.objects.filter(
            status=ParserProductClassification.STATUS_ACTIVE,
        ).exclude(
            product_key__in=(product_keys | preserved_manual_keys),
        ).update(
            status=ParserProductClassification.STATUS_INACTIVE,
            date_update=now,
        )
        existing = {
            row.product_key: row
            for row in ParserProductClassification.objects.select_for_update().filter(
                product_key__in=product_keys,
            )
        }
        create_rows, update_rows = [], []
        for product_key, values in classifications.items():
            obj = existing.get(product_key)
            if obj is None:
                obj = ParserProductClassification(product_key=product_key)
                create_rows.append(obj)
            else:
                update_rows.append(obj)
            for field, value in values.items():
                setattr(obj, field, value or None)
            obj.url = url_by_key.get(product_key) or None
            obj.status = ParserProductClassification.STATUS_ACTIVE
            obj.date_update = now
        if create_rows:
            ParserProductClassification.objects.bulk_create(create_rows, batch_size=500)
        if update_rows:
            ParserProductClassification.objects.bulk_update(
                update_rows,
                fields=(
                    "category", "subcategory", "subcategory_type", "color",
                    "material", "modification", "article_number_analogs",
                    "item_type", "url", "status", "date_update",
                ),
                batch_size=500,
            )

        ParserProductMatch.objects.filter(
            match_type=ParserProductMatch.MATCH_TYPE_AUTO,
        ).update(status=ParserProductMatch.STATUS_INACTIVE)
        rows = [
            ParserProductMatch(
                product_key_base=base_key,
                product_key_competitor=competitor_key,
                match_type=ParserProductMatch.MATCH_TYPE_AUTO,
                status=ParserProductMatch.STATUS_ACTIVE,
            )
            for base_key, competitor_key in sorted(active_automatic_pairs)
        ]
        if rows:
            ParserProductMatch.objects.bulk_create(
                rows,
                update_conflicts=True,
                update_fields=("status", "match_type"),
                unique_fields=("product_key_base", "product_key_competitor"),
                batch_size=500,
            )
        images_updated = sync_iprice_product_images(
            product_keys=product_keys,
        )["classifications_updated"]

    return {
        "status": "success",
        "filename": filename,
        "input_rows": input_rows,
        "classifications_loaded": len(classifications),
        "automatic_matches_loaded": len(active_automatic_pairs),
        "excluded_matches_preserved": len(automatic_pairs & excluded_pairs),
        "skipped_rows": skipped,
        "images_updated": images_updated,
    }
