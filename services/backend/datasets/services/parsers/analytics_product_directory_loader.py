from __future__ import annotations

import hashlib
import json
from zipfile import BadZipFile
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from datasets.models import (
    AnalyticsProductClassificationPrice,
    AnalyticsProductClassificationPriority,
    AnalyticsProductClassificationProperty,
    AnalyticsProductClassificationScoreProfile,
    AnalyticsProductClassificationScoreWeight,
    AnalyticsProductDirectoryLoad,
    AnalyticsProductManyToManyRule,
    AnalyticsProductManualProperty,
    AnalyticsProductMatchingScoreProfile,
    AnalyticsProductMatchingScoreWeight,
    AnalyticsProductModificationRule,
    AnalyticsProductNumericalMetric,
    AnalyticsProductPriceRule,
    AnalyticsProductPropertyRule,
    AnalyticsProductScoringThreshold,
    AnalyticsProductSourcePriority,
    BaseProductPrice,
    PsProductPrice,
    TaraProductPrice,
    TtProductPrice,
    ParserProductUrl,
)


class ProductDirectoryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SheetSpec:
    headers: tuple[str, ...]


SPECS = {
    "price_tables": SheetSpec((
        "source", "normalized_property", "table", "field", "value",
        "name_property", "property_type",
    )),
    "property tables": SheetSpec((
        "source", "normalized_property", "table", "field", "field_text",
        "value", "name_property", "property_type",
    )),
    "modification": SheetSpec((
        "name_property", "render_group", "group_priority",
        "property_priority", "value_type", "canonical_unit", "render_rule",
        "template_true", "template_false", "template_value", "value_map",
        "dependency", "include_rule", "example", "rule_note",
    )),
    "classification_score": SheetSpec((
        "item_type", "category", "subcategory", "subcategory_type",
        "score_profile", "insertion", "cover_included", "wheel_included",
        "legs_included", "opening_pedal_included", "runner_included",
        "drain_hole_included", "brake_included", "bottom_type", "walls_type",
        "support_type", "handles", "tap_included", "runner_number",
        "wheel_diameter", "wheel_number", "volume", "weight", "height",
        "width", "length", "thickness", "density", "diameter",
        "drain_hole_diameter", "base_diameter", "total_weight", "rule_note",
    )),
    "classification_price": SheetSpec((
        "source", "item_type", "category", "subcategory", "subcategory_type",
        "table", "field_subcategory", "value", "table",
        "field_subcategory_type", "value",
    )),
    "classification_property": SheetSpec((
        "source", "item_type", "category", "subcategory", "subcategory_type",
        "table", "field_subcategory", "value", "table",
        "field_subcategory_type", "field_text", "value",
    )),
    "numerical_metrics": SheetSpec((
        "metrics_name", "number_format", "measurability", "limit", "check",
    )),
    "many_to_many": SheetSpec(("code", "handler_name", "description")),
    "matching_score": SheetSpec((
        "item_type", "category", "subcategory", "subcategory_type",
        "score_profile", "material", "color", "insertion", "cover_included",
        "wheel_included", "legs_included", "opening_pedal_included",
        "runner_included", "drain_hole_included", "brake_included",
        "bottom_type", "walls_type", "support_type", "handles", "tap_included",
        "runner_number", "wheel_diameter", "wheel_number", "volume", "weight",
        "height", "width", "length", "thickness", "density", "diameter",
        "drain_hole_diameter", "base_diameter", "total_weight", "rule_note",
    )),
    "scoring_thresholds": SheetSpec((
        "metric", "level", "min_value", "max_value", "status", "auto_action",
        "rule_note",
    )),
    "classification_priority": SheetSpec((
        "stage", "rule_source", "rule_kind", "priority", "specificity_order",
        "tie_breaker", "rule_note",
    )),
    "manual_properties": SheetSpec((
        "product_key", "property_name", "value",
    )),
}

ALLOW_EMPTY_SHEETS = {"manual_properties"}

ALLOWED_SOURCES = {"base", "tt", "tara", "ps"}
ALLOWED_PROPERTY_TYPES = {"letter", "numerical"}
ALLOWED_ITEM_TYPES = {"product", "component"}
ALLOWED_THRESHOLD_METRICS = {
    "classification_score", "match_score", "match_coverage", "match_gap",
    "subcategory_type", "matching_property_weight",
}
ALLOWED_THRESHOLD_ACTIONS = {
    "auto_accept", "manual_control", "do_not_auto_classify", "auto_match",
    "do_not_match", "auto_match_allowed", "do_not_auto_match",
    "normal_candidate_pool", "subcategory_candidate_pool",
    "require_exact_match",
}
MAX_DIRECTORY_FILE_SIZE = 20 * 1024 * 1024
KNOWN_HANDLERS = {
    "match_any_color", "color_missing", "extract_dimension_length",
    "extract_dimension_width", "extract_dimension_height",
    "default_tt_material_pe_pp", "extract_runner_number_from_name",
    "extract_wheel_diameter_from_name", "extract_wheel_number_from_name",
    "extract_volume_from_name",
}
DEFAULT_SOURCE_PRIORITIES = (
    ("base", 10, "parser_product_property", "property"),
    ("base", 20, "base_product_price", "price"),
    ("base", 30, "base_product_price", "name"),
    ("tt", 10, "tt_product_price", "price"),
    ("tt", 20, "parser_product_property", "property"),
    ("tt", 30, "tt_product_price", "name"),
    ("tara", 10, "parser_product_property", "property"),
    ("tara", 20, "tara_product_price", "price"),
    ("tara", 30, "tara_product_price", "name"),
    ("ps", 10, "parser_product_property", "property"),
    ("ps", 20, "ps_product_price", "price"),
    ("ps", 30, "ps_product_price", "name"),
)
SOURCE_PRICE_MODELS = {
    "base": BaseProductPrice,
    "tt": TtProductPrice,
    "tara": TaraProductPrice,
    "ps": PsProductPrice,
}
SOURCE_PRICE_TABLES = {
    source: model._meta.db_table
    for source, model in SOURCE_PRICE_MODELS.items()
}


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _decimal(value, *, location):
    try:
        return Decimal(_clean(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ProductDirectoryValidationError(
            f"{location}: ожидалось число, получено {value!r}"
        ) from exc


def _checksum(file_obj):
    size = getattr(file_obj, "size", None)
    if size is not None and size > MAX_DIRECTORY_FILE_SIZE:
        raise ProductDirectoryValidationError(
            "directory.xlsx превышает допустимый размер 20 МБ"
        )
    digest = hashlib.sha256()
    file_obj.seek(0)
    total = 0
    while True:
        chunk = file_obj.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_DIRECTORY_FILE_SIZE:
            raise ProductDirectoryValidationError(
                "directory.xlsx превышает допустимый размер 20 МБ"
            )
        digest.update(chunk)
    file_obj.seek(0)
    return digest.hexdigest()


def _read_sheets(file_obj):
    file_obj.seek(0)
    try:
        workbook = load_workbook(file_obj, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as exc:
        raise ProductDirectoryValidationError(
            f"Не удалось прочитать directory.xlsx: {exc}"
        ) from exc
    try:
        return _read_workbook(workbook)
    finally:
        workbook.close()


def _read_workbook(workbook):
    missing = [name for name in SPECS if name not in workbook.sheetnames]
    extra = [name for name in workbook.sheetnames if name not in SPECS]
    if missing or extra:
        raise ProductDirectoryValidationError(
            f"Некорректный набор листов: отсутствуют={missing}, лишние={extra}"
        )

    result = {}
    for name, spec in SPECS.items():
        worksheet = workbook[name]
        if worksheet.max_row > 10000 or worksheet.max_column > len(spec.headers) + 5:
            raise ProductDirectoryValidationError(
                f"Лист {name!r} имеет недопустимый размер "
                f"{worksheet.max_row}x{worksheet.max_column}"
            )
        raw_rows = list(worksheet.iter_rows(values_only=True))
        if not raw_rows:
            raise ProductDirectoryValidationError(f"Лист {name!r} пуст")
        header = tuple(_clean(value) for value in raw_rows[0])
        while header and not header[-1]:
            header = header[:-1]
        if header != spec.headers:
            raise ProductDirectoryValidationError(
                f"Лист {name!r}: ожидаются колонки {spec.headers}, получены {header}"
            )
        rows = []
        for row_number, raw in enumerate(raw_rows[1:], 2):
            values = tuple(raw[:len(spec.headers)])
            if not any(_clean(value) for value in values):
                continue
            rows.append((row_number, values))
        if not rows and name not in ALLOW_EMPTY_SHEETS:
            raise ProductDirectoryValidationError(
                f"Лист {name!r} не содержит строк данных"
            )
        normalized = [tuple(_clean(value) for value in row) for _, row in rows]
        duplicates = [row for row, count in Counter(normalized).items() if count > 1]
        if duplicates:
            raise ProductDirectoryValidationError(
                f"Лист {name!r}: найдены идентичные дубликаты: {duplicates[:3]}"
            )
        result[name] = rows
    return result


def _validate_delimited_rule(field_text, value, *, location):
    field_text = _clean(field_text)
    value = _clean(value)
    if ";" in field_text or ";" in value:
        raise ProductDirectoryValidationError(
            f"{location}: старый разделитель ';' запрещён"
        )
    field_and = field_text.split("///")
    value_and = value.split("///")
    if len(field_and) != len(value_and):
        raise ProductDirectoryValidationError(
            f"{location}: число позиционных AND-групп не совпадает"
        )
    for group in (*field_and, *value_and):
        if not group or any(not part.strip() for part in group.split("//")):
            raise ProductDirectoryValidationError(
                f"{location}: пустая OR/AND-группа"
            )


def _validate(rows):
    metrics = {}
    for row_number, row in rows["numerical_metrics"]:
        name, number_format, unit, tolerance, _ = row
        name = _clean(name)
        if name in metrics:
            raise ProductDirectoryValidationError(
                f"numerical_metrics:{row_number}: повтор metrics_name={name!r}"
            )
        if _clean(number_format) not in {"integer", "decimal"}:
            raise ProductDirectoryValidationError(
                f"numerical_metrics:{row_number}: некорректный number_format"
            )
        tolerance_value = _decimal(
            tolerance, location=f"numerical_metrics:{row_number}:limit"
        )
        if tolerance_value < 0:
            raise ProductDirectoryValidationError(
                f"numerical_metrics:{row_number}: limit не может быть отрицательным"
            )
        metrics[name] = (_clean(unit), tolerance_value)

    handlers = {}
    for row_number, row in rows["many_to_many"]:
        code, handler_name, _ = map(_clean, row)
        if not code.startswith("MANY-TO-MANY_"):
            raise ProductDirectoryValidationError(
                f"many_to_many:{row_number}: некорректный code={code!r}"
            )
        if handler_name not in KNOWN_HANDLERS:
            raise ProductDirectoryValidationError(
                f"many_to_many:{row_number}: неизвестный handler={handler_name!r}"
            )
        if code in handlers:
            raise ProductDirectoryValidationError(
                f"many_to_many:{row_number}: повтор code={code!r}"
            )
        handlers[code] = handler_name

    modification_properties = set()
    for row_number, row in rows["modification"]:
        property_name = _clean(row[0])
        if not property_name:
            raise ProductDirectoryValidationError(
                f"modification:{row_number}: name_property не заполнен"
            )
        if property_name in modification_properties:
            raise ProductDirectoryValidationError(
                f"modification:{row_number}: повтор name_property={property_name!r}"
            )
        modification_properties.add(property_name)

    known_manual_properties = set(
        SPECS["matching_score"].headers[5:-2]
    )
    manual_keys = set()
    manual_product_keys = set()
    for row_number, row in rows["manual_properties"]:
        product_key_value = _decimal(
            row[0], location=f"manual_properties:{row_number}:product_key"
        )
        if product_key_value <= 0 or product_key_value != product_key_value.to_integral_value():
            raise ProductDirectoryValidationError(
                f"manual_properties:{row_number}: product_key должен быть положительным целым"
            )
        product_key = int(product_key_value)
        property_name = _clean(row[1])
        value = _clean(row[2])
        if property_name not in known_manual_properties:
            raise ProductDirectoryValidationError(
                f"manual_properties:{row_number}: неизвестное свойство {property_name!r}"
            )
        if not value:
            raise ProductDirectoryValidationError(
                f"manual_properties:{row_number}: value не заполнено"
            )
        key = (product_key, property_name)
        if key in manual_keys:
            raise ProductDirectoryValidationError(
                f"manual_properties:{row_number}: повтор product_key + property_name {key!r}"
            )
        if property_name in metrics:
            _decimal(value, location=f"manual_properties:{row_number}:value")
        manual_keys.add(key)
        manual_product_keys.add(product_key)

    existing_manual_product_keys = set(
        ParserProductUrl.objects.filter(
            id__in=manual_product_keys,
        ).values_list("id", flat=True)
    )
    missing_manual_product_keys = sorted(
        manual_product_keys - existing_manual_product_keys
    )
    if missing_manual_product_keys:
        raise ProductDirectoryValidationError(
            "manual_properties: не найдены product_key: "
            + ", ".join(str(value) for value in missing_manual_product_keys[:20])
        )

    for sheet_name in ("price_tables", "property tables"):
        for row_number, row in rows[sheet_name]:
            source = _clean(row[0])
            normalized_property = _clean(row[1])
            property_name = _clean(row[-2])
            property_type = _clean(row[-1])
            if source not in ALLOWED_SOURCES:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: неизвестный source={source!r}"
                )
            if property_type not in ALLOWED_PROPERTY_TYPES:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: property_type={property_type!r}"
                )
            if property_type == "numerical" and property_name not in metrics:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: нет numerical_metrics для {property_name!r}"
                )
            source_table = _clean(row[2])
            source_field = _clean(row[3])
            if sheet_name == "price_tables":
                if source_table != SOURCE_PRICE_TABLES[source]:
                    raise ProductDirectoryValidationError(
                        f"{sheet_name}:{row_number}: table={source_table!r} "
                        f"не соответствует source={source!r}"
                    )
                model_fields = {
                    field.name for field in SOURCE_PRICE_MODELS[source]._meta.concrete_fields
                }
                if source_field not in model_fields:
                    raise ProductDirectoryValidationError(
                        f"{sheet_name}:{row_number}: поле {source_field!r} "
                        f"отсутствует в {source_table}"
                    )
            elif source_table != "parser_product_property" or source_field != "properties":
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: ожидаются "
                    "table=parser_product_property и field=properties"
                )
            for value in row:
                text = _clean(value)
                if text.startswith("MANY-TO-MANY_") and text not in handlers:
                    raise ProductDirectoryValidationError(
                        f"{sheet_name}:{row_number}: неизвестная ссылка {text!r}"
                    )
            if not normalized_property:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: normalized_property пуст"
                )

    for sheet_name in ("classification_price", "classification_property"):
        for row_number, row in rows[sheet_name]:
            required = row[:8]
            if any(not _clean(value) for value in required):
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: пустое обязательное поле классификации"
                )
            if _clean(row[0]) not in ALLOWED_SOURCES:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: неизвестный source={row[0]!r}"
                )
            if _clean(row[1]) not in ALLOWED_ITEM_TYPES:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: неизвестный item_type={row[1]!r}"
                )
            source = _clean(row[0])
            expected_price_table = SOURCE_PRICE_TABLES[source]
            if _clean(row[5]) != expected_price_table or _clean(row[6]) != "name":
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: subcategory должна определяться "
                    f"по {expected_price_table}.name"
                )
            expected_type_table = (
                "parser_product_property"
                if sheet_name == "classification_property"
                else expected_price_table
            )
            expected_type_field = (
                "properties" if sheet_name == "classification_property" else "name"
            )
            if _clean(row[8]) != expected_type_table or _clean(row[9]) != expected_type_field:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: некорректный источник "
                    "условия subcategory_type"
                )
            if sheet_name == "classification_property":
                if any(not _clean(value) for value in row[8:12]):
                    raise ProductDirectoryValidationError(
                        f"{sheet_name}:{row_number}: пустое условие subcategory_type"
                    )
                _validate_delimited_rule(
                    row[10], row[11], location=f"{sheet_name}:{row_number}"
                )
            elif any(not _clean(value) for value in row[8:11]):
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: пустое условие subcategory_type"
                )

    profile_keys = {}
    for sheet_name in ("classification_score", "matching_score"):
        keys = set()
        for row_number, row in rows[sheet_name]:
            key = tuple(_clean(value) for value in row[:4])
            if any(not value for value in key):
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: пустой ключ профиля"
                )
            if key in keys:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: повтор ключа профиля {key!r}"
                )
            weights = [
                _decimal(value, location=f"{sheet_name}:{row_number}")
                for value in row[5:-2]
            ]
            total = _decimal(row[-2], location=f"{sheet_name}:{row_number}:total")
            if total != Decimal("100") or sum(weights) != total:
                raise ProductDirectoryValidationError(
                    f"{sheet_name}:{row_number}: веса должны давать ровно 100"
                )
            keys.add(key)
        profile_keys[sheet_name] = keys
    if profile_keys["classification_score"] != profile_keys["matching_score"]:
        raise ProductDirectoryValidationError(
            "Ключи classification_score и matching_score не совпадают"
        )

    thresholds_by_metric = {}
    for row_number, row in rows["scoring_thresholds"]:
        metric = _clean(row[0])
        status = _clean(row[4])
        action = _clean(row[5])
        if metric not in ALLOWED_THRESHOLD_METRICS:
            raise ProductDirectoryValidationError(
                f"scoring_thresholds:{row_number}: неизвестный metric={metric!r}"
            )
        if not status:
            raise ProductDirectoryValidationError(
                f"scoring_thresholds:{row_number}: status не заполнен"
            )
        if action not in ALLOWED_THRESHOLD_ACTIONS:
            raise ProductDirectoryValidationError(
                f"scoring_thresholds:{row_number}: неизвестный auto_action={action!r}"
            )
        minimum = (
            _decimal(row[2], location=f"scoring_thresholds:{row_number}:min_value")
            if _clean(row[2]) else None
        )
        maximum = (
            _decimal(row[3], location=f"scoring_thresholds:{row_number}:max_value")
            if _clean(row[3]) else None
        )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ProductDirectoryValidationError(
                f"scoring_thresholds:{row_number}: min_value больше max_value"
            )
        if metric in {
            "classification_score", "match_score", "match_coverage", "match_gap",
            "matching_property_weight",
        }:
            for value in (minimum, maximum):
                if value is not None and not Decimal("0") <= value <= Decimal("100"):
                    raise ProductDirectoryValidationError(
                        f"scoring_thresholds:{row_number}: порог должен быть от 0 до 100"
                    )
        thresholds_by_metric.setdefault(metric, []).append(row)

    required_actions = {
        "classification_score": "auto_accept",
        "match_score": "auto_match",
        "match_coverage": "auto_match_allowed",
        "match_gap": "auto_match_allowed",
        "matching_property_weight": "require_exact_match",
    }
    for metric, action in required_actions.items():
        metric_rows = thresholds_by_metric.get(metric, ())
        if not any(_clean(row[5]) == action for row in metric_rows):
            raise ProductDirectoryValidationError(
                f"scoring_thresholds: для {metric} отсутствует auto_action={action}"
            )
        ranges = sorted(
            (
                _decimal(row[2], location=f"scoring_thresholds:{metric}:min")
                if _clean(row[2]) else Decimal("0"),
                _decimal(row[3], location=f"scoring_thresholds:{metric}:max")
                if _clean(row[3]) else Decimal("100"),
            )
            for row in metric_rows
        )
        for previous, current in zip(ranges, ranges[1:]):
            if current[0] <= previous[1]:
                raise ProductDirectoryValidationError(
                    f"scoring_thresholds: диапазоны {metric} пересекаются"
                )


def _json_map(value, *, location):
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProductDirectoryValidationError(
            f"{location}: value_map должен быть JSON object"
        ) from exc
    if not isinstance(parsed, dict):
        raise ProductDirectoryValidationError(
            f"{location}: value_map должен быть JSON object"
        )
    return parsed


def _replace_reference_tables(rows):
    # Dependent weights are removed by profile cascades.
    for model in (
        AnalyticsProductClassificationScoreProfile,
        AnalyticsProductMatchingScoreProfile,
        AnalyticsProductPriceRule,
        AnalyticsProductPropertyRule,
        AnalyticsProductClassificationPrice,
        AnalyticsProductClassificationProperty,
        AnalyticsProductNumericalMetric,
        AnalyticsProductManyToManyRule,
        AnalyticsProductManualProperty,
        AnalyticsProductModificationRule,
        AnalyticsProductScoringThreshold,
        AnalyticsProductClassificationPriority,
        AnalyticsProductSourcePriority,
    ):
        model.objects.all().delete()

    AnalyticsProductPriceRule.objects.bulk_create([
        AnalyticsProductPriceRule(
            source=_clean(r[0]), normalized_property=_clean(r[1]),
            source_table=_clean(r[2]), source_field=_clean(r[3]),
            source_value=_clean(r[4]), property_name=_clean(r[5]),
            property_type=_clean(r[6]),
        ) for _, r in rows["price_tables"]
    ], batch_size=1000)
    AnalyticsProductPropertyRule.objects.bulk_create([
        AnalyticsProductPropertyRule(
            source=_clean(r[0]), normalized_property=_clean(r[1]),
            source_table=_clean(r[2]), source_field=_clean(r[3]),
            field_text=_clean(r[4]), source_value=_clean(r[5]),
            property_name=_clean(r[6]), property_type=_clean(r[7]),
        ) for _, r in rows["property tables"]
    ], batch_size=1000)
    AnalyticsProductManualProperty.objects.bulk_create([
        AnalyticsProductManualProperty(
            product_key=int(_decimal(
                r[0], location=f"manual_properties:{n}:product_key"
            )),
            property_name=_clean(r[1]),
            value=_clean(r[2]),
        )
        for n, r in rows["manual_properties"]
    ], batch_size=1000)

    common = lambda r: dict(
        source=_clean(r[0]), item_type=_clean(r[1]), category=_clean(r[2]),
        subcategory=_clean(r[3]), subcategory_type=_clean(r[4]),
        subcategory_table=_clean(r[5]), subcategory_field=_clean(r[6]),
        subcategory_value=_clean(r[7]), subcategory_type_table=_clean(r[8]),
        subcategory_type_field=_clean(r[9]),
    )
    AnalyticsProductClassificationPrice.objects.bulk_create([
        AnalyticsProductClassificationPrice(
            **common(r), subcategory_type_value=_clean(r[10])
        ) for _, r in rows["classification_price"]
    ], batch_size=1000)
    AnalyticsProductClassificationProperty.objects.bulk_create([
        AnalyticsProductClassificationProperty(
            **common(r), subcategory_type_field_text=_clean(r[10]),
            subcategory_type_value=_clean(r[11]),
        ) for _, r in rows["classification_property"]
    ], batch_size=1000)

    AnalyticsProductNumericalMetric.objects.bulk_create([
        AnalyticsProductNumericalMetric(
            metrics_name=_clean(r[0]), number_format=_clean(r[1]),
            measurability=_clean(r[2]),
            tolerance=_decimal(r[3], location=f"numerical_metrics:{n}"),
            check_note=_clean(r[4]),
        ) for n, r in rows["numerical_metrics"]
    ])
    AnalyticsProductManyToManyRule.objects.bulk_create([
        AnalyticsProductManyToManyRule(
            code=_clean(r[0]), handler_name=_clean(r[1]), description=_clean(r[2])
        ) for _, r in rows["many_to_many"]
    ])
    AnalyticsProductModificationRule.objects.bulk_create([
        AnalyticsProductModificationRule(
            property_name=_clean(r[0]), render_group=_clean(r[1]),
            group_priority=int(_decimal(r[2], location=f"modification:{n}")),
            property_priority=int(_decimal(r[3], location=f"modification:{n}")),
            value_type=_clean(r[4]), canonical_unit=_clean(r[5]),
            render_rule=_clean(r[6]), template_true=_clean(r[7]),
            template_false=_clean(r[8]), template_value=_clean(r[9]),
            value_map=_json_map(r[10], location=f"modification:{n}"),
            dependency=_clean(r[11]), include_rule=_clean(r[12]),
            example=_clean(r[13]), rule_note=_clean(r[14]),
        ) for n, r in rows["modification"]
    ])

    score_property_start = 5
    for sheet_name, profile_model, weight_model in (
        ("classification_score", AnalyticsProductClassificationScoreProfile,
         AnalyticsProductClassificationScoreWeight),
        ("matching_score", AnalyticsProductMatchingScoreProfile,
         AnalyticsProductMatchingScoreWeight),
    ):
        headers = SPECS[sheet_name].headers
        property_names = headers[score_property_start:-2]
        for row_number, r in rows[sheet_name]:
            profile = profile_model.objects.create(
                item_type=_clean(r[0]), category=_clean(r[1]),
                subcategory=_clean(r[2]), subcategory_type=_clean(r[3]),
                score_profile=_clean(r[4]),
                total_weight=_decimal(r[-2], location=f"{sheet_name}:{row_number}"),
                rule_note=_clean(r[-1]),
            )
            weight_model.objects.bulk_create([
                weight_model(
                    profile=profile, property_name=name,
                    weight=_decimal(value, location=f"{sheet_name}:{row_number}:{name}"),
                ) for name, value in zip(property_names, r[score_property_start:-2])
            ])

    AnalyticsProductScoringThreshold.objects.bulk_create([
        AnalyticsProductScoringThreshold(
            metric=_clean(r[0]), level=_clean(r[1]),
            min_value=(None if not _clean(r[2]) else _decimal(r[2], location=f"threshold:{n}")),
            max_value=(None if not _clean(r[3]) else _decimal(r[3], location=f"threshold:{n}")),
            status=_clean(r[4]), auto_action=_clean(r[5]), rule_note=_clean(r[6]),
        ) for n, r in rows["scoring_thresholds"]
    ])
    AnalyticsProductClassificationPriority.objects.bulk_create([
        AnalyticsProductClassificationPriority(
            stage=_clean(r[0]), rule_source=_clean(r[1]), rule_kind=_clean(r[2]),
            priority=int(_decimal(r[3], location=f"priority:{n}")),
            specificity_order=int(_decimal(r[4], location=f"priority:{n}")),
            tie_breaker=_clean(r[5]), rule_note=_clean(r[6]),
        ) for n, r in rows["classification_priority"]
    ])
    AnalyticsProductSourcePriority.objects.bulk_create([
        AnalyticsProductSourcePriority(
            source=source, priority=priority, source_table=table,
            extraction_scope=scope,
        ) for source, priority, table, scope in DEFAULT_SOURCE_PRIORITIES
    ])


def load_analytics_product_directory(file_obj, *, filename=None):
    checksum = _checksum(file_obj)
    directory_load = AnalyticsProductDirectoryLoad.objects.create(
        filename=filename or getattr(file_obj, "name", "directory.xlsx"),
        checksum=checksum,
    )
    try:
        rows = _read_sheets(file_obj)
        _validate(rows)
        with transaction.atomic():
            _replace_reference_tables(rows)
            directory_load.status = AnalyticsProductDirectoryLoad.STATUS_SUCCESS
            directory_load.rows_loaded = {
                sheet: len(values) for sheet, values in rows.items()
            }
            directory_load.finished_at = timezone.now()
            directory_load.save(update_fields=(
                "status", "rows_loaded", "finished_at",
            ))
    except Exception as exc:
        directory_load.status = AnalyticsProductDirectoryLoad.STATUS_FAILED
        directory_load.error_text = str(exc)
        directory_load.finished_at = timezone.now()
        directory_load.save(update_fields=("status", "error_text", "finished_at"))
        raise
    return directory_load
