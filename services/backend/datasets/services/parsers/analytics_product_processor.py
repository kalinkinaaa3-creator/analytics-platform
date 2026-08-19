from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from datasets.models import (
    AnalyticsProductAnalysisResult,
    AnalyticsProductClassificationPrice,
    AnalyticsProductClassificationPriority,
    AnalyticsProductClassificationProperty,
    AnalyticsProductClassificationScoreProfile,
    AnalyticsProductManyToManyRule,
    AnalyticsProductManualProperty,
    AnalyticsProductMatchCandidate,
    AnalyticsProductMatchingScoreProfile,
    AnalyticsProductModificationRule,
    AnalyticsProductNumericalMetric,
    AnalyticsProductPriceRule,
    AnalyticsProductProcessingRun,
    AnalyticsProductPropertyRule,
    AnalyticsProductScoringThreshold,
    AnalyticsProductSourcePriority,
    BaseProductPrice,
    ParserProductProperty,
    ParserProductUrl,
    PsProductPrice,
    TaraProductPrice,
    TtProductPrice,
)
from datasets.services.parsers.analytics_product_normalization import (
    contains_phrase,
    extract_dimension,
    normalize_numeric,
    normalize_text,
    run_many_to_many_handler,
    split_and,
    split_or,
)
from datasets.services.parsers.analytics_product_property_labels import (
    get_match_property_label,
)
from datasets.services.parsers.analytics_product_lock import (
    analytics_product_operation_lock,
)


logger = logging.getLogger("analytics_product.processor")

PRODUCT_BATCH_SIZE = 200
RESULT_BATCH_SIZE = 200
QUERY_CHUNK_SIZE = 500
PROPERTY_HANDLER_REQUIRES_VALUE_MATCH = {
    "match_any_color",
}

SOURCE_MODELS = {
    "base": BaseProductPrice,
    "tt": TtProductPrice,
    "tara": TaraProductPrice,
    "ps": PsProductPrice,
}


@dataclass
class SourceProduct:
    product_key: int
    source: str
    name: str
    url: str
    image: str
    price_fields: dict
    raw_properties: dict


@dataclass
class ClassificationDecision:
    item_type: str = ""
    category: str = ""
    subcategory: str = ""
    subcategory_type: str = ""
    ambiguous: bool = False
    evidence: dict | None = None


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _chunks(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class DirectoryRuntime:
    """Small immutable-in-practice cache of directory rules, not products."""

    def __init__(self):
        self.metrics = {
            row.metrics_name: row
            for row in AnalyticsProductNumericalMetric.objects.all().iterator(
                chunk_size=QUERY_CHUNK_SIZE
            )
        }
        self.manual_properties = defaultdict(dict)
        for row in AnalyticsProductManualProperty.objects.all().order_by("id").iterator(
            chunk_size=QUERY_CHUNK_SIZE
        ):
            self.manual_properties[row.product_key][row.property_name] = row.value
        self.handlers = {
            row.code: row.handler_name
            for row in AnalyticsProductManyToManyRule.objects.all().iterator(
                chunk_size=QUERY_CHUNK_SIZE
            )
        }
        self.price_rules = defaultdict(list)
        for rule in AnalyticsProductPriceRule.objects.all().order_by("id").iterator(
            chunk_size=QUERY_CHUNK_SIZE
        ):
            self.price_rules[rule.source].append(rule)
        self.property_rules = defaultdict(list)
        for rule in AnalyticsProductPropertyRule.objects.all().order_by("id").iterator(
            chunk_size=QUERY_CHUNK_SIZE
        ):
            self.property_rules[rule.source].append(rule)
        self.classification_price = defaultdict(list)
        for rule in AnalyticsProductClassificationPrice.objects.all().order_by("id").iterator(
            chunk_size=QUERY_CHUNK_SIZE
        ):
            self.classification_price[rule.source].append(rule)
        self.classification_property = defaultdict(list)
        for rule in AnalyticsProductClassificationProperty.objects.all().order_by("id").iterator(
            chunk_size=QUERY_CHUNK_SIZE
        ):
            self.classification_property[rule.source].append(rule)
        self.subcategories_with_types = {
            normalize_text(rule.subcategory)
            for rules_by_source in (
                self.classification_price.values(),
                self.classification_property.values(),
            )
            for rules in rules_by_source
            for rule in rules
            if normalize_text(rule.subcategory_type)
        }
        self.sources = sorted(
            set(self.classification_price) | set(self.classification_property),
            key=lambda value: (value != "base", value),
        )
        self.priorities = {
            (row.stage, row.rule_source, row.rule_kind): row.priority
            for row in AnalyticsProductClassificationPriority.objects.all().iterator(
                chunk_size=QUERY_CHUNK_SIZE
            )
        }
        self.source_priorities = {
            (row.source, row.source_table, row.extraction_scope): row.priority
            for row in AnalyticsProductSourcePriority.objects.all().iterator(
                chunk_size=QUERY_CHUNK_SIZE
            )
        }
        self.modification_rules = list(
            AnalyticsProductModificationRule.objects.all().order_by(
                "group_priority", "property_priority", "id"
            )
        )
        self.classification_profiles = self._profiles(
            AnalyticsProductClassificationScoreProfile
        )
        self.matching_profiles = self._profiles(AnalyticsProductMatchingScoreProfile)
        self.thresholds = defaultdict(list)
        for row in AnalyticsProductScoringThreshold.objects.all().order_by(
            "metric", "min_value", "id"
        ).iterator(
            chunk_size=QUERY_CHUNK_SIZE
        ):
            self.thresholds[row.metric].append(row)
        if not any(
            row.auto_action == "require_exact_match"
            for row in self.thresholds.get("matching_property_weight", ())
        ):
            raise ValueError(
                "В scoring_thresholds отсутствует настройка "
                "matching_property_weight с auto_action=require_exact_match"
            )

    @staticmethod
    def _profiles(model):
        result = {}
        queryset = model.objects.prefetch_related("weights").all()
        for profile in queryset.iterator(chunk_size=100):
            key = (
                normalize_text(profile.item_type),
                normalize_text(profile.category),
                normalize_text(profile.subcategory),
                normalize_text(profile.subcategory_type),
            )
            result[key] = {
                "code": profile.score_profile,
                "total": profile.total_weight,
                "weights": {
                    weight.property_name: weight.weight
                    for weight in profile.weights.all()
                    if weight.weight > 0
                },
            }
        return result

    def profile(self, mapping, decision):
        key = tuple(normalize_text(value) for value in (
            decision.item_type, decision.category, decision.subcategory,
            decision.subcategory_type,
        ))
        return mapping.get(key)

    def threshold(self, metric, value):
        value = Decimal(str(value))
        for row in self.thresholds.get(metric, ()):
            if row.min_value is not None and value < row.min_value:
                continue
            if row.max_value is not None and value > row.max_value:
                continue
            return row
        return None


def _latest_price_rows(model, source, requested_fields=()):
    fields = ["product_key", "name", "url", "image"]
    if source in {"base", "tara", "ps"}:
        fields.append("color")
    elif source == "tt":
        fields.append("additional_property")
    model_fields = {field.name for field in model._meta.concrete_fields}
    for field in requested_fields:
        if field not in model_fields:
            raise ValueError(
                f"Источник {source}: поле price_tables {field!r} отсутствует в {model.__name__}"
            )
        if field not in fields:
            fields.append(field)
    active_product_keys = ParserProductUrl.objects.filter(
        source=source,
        status=ParserProductUrl.STATUS_ACTIVE,
    ).values("id")
    queryset = (
        model.objects.filter(
            product_key__in=active_product_keys,
        ).annotate(
            latest_row_number=Window(
                expression=RowNumber(), partition_by=(F("product_key"),),
                order_by=(F("date_add").desc(), F("id").desc()),
            )
        )
        .filter(latest_row_number=1)
        .order_by("product_key")
        .values(*fields)
    )
    for row in queryset.iterator(chunk_size=QUERY_CHUNK_SIZE):
        yield row


def _raw_properties_for_batch(source, product_keys):
    result = defaultdict(dict)
    seen = set()
    queryset = (
        ParserProductProperty.objects.filter(source=source, product_key__in=product_keys)
        .order_by("product_key", "properties", "-date_add", "-id")
        .values("product_key", "properties", "value")
    )
    for row in queryset.iterator(chunk_size=QUERY_CHUNK_SIZE):
        key = (row["product_key"], normalize_text(row["properties"]))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result[row["product_key"]][key[1]] = row["value"]
    return result


def iter_source_products(model, source, requested_fields=()):
    for batch in _chunks(
        _latest_price_rows(model, source, requested_fields), PRODUCT_BATCH_SIZE
    ):
        keys = [row["product_key"] for row in batch]
        properties = _raw_properties_for_batch(source, keys)
        for row in batch:
            yield SourceProduct(
                product_key=row["product_key"], source=source,
                name=row.get("name") or "", url=row.get("url") or "",
                image=row.get("image") or "", price_fields=row,
                raw_properties=properties.get(row["product_key"], {}),
            )


def _first_raw_property(raw_properties, field_expression):
    # ``//`` means left-to-right alternatives. The first present non-empty
    # property wins for positional rules.
    for alternative in split_or(field_expression):
        value = raw_properties.get(normalize_text(alternative))
        if value not in (None, ""):
            return value, alternative
    return None, None


def _rule_handler(runtime, *values):
    for value in values:
        text = str(value or "").strip()
        if text in runtime.handlers:
            return runtime.handlers[text]
    return None


def _numeric_property(runtime, property_name, raw_value):
    metric = runtime.metrics.get(property_name)
    if not metric:
        return None
    return normalize_numeric(
        raw_value,
        canonical_unit=metric.measurability,
        number_format=metric.number_format,
    )


def extract_normalized_properties(runtime, product):
    candidates = defaultdict(list)

    for rule in runtime.property_rules[product.source]:
        raw_value, matched_field = _first_raw_property(
            product.raw_properties, rule.field_text
        )
        if raw_value in (None, ""):
            continue
        handler = _rule_handler(runtime, rule.normalized_property, rule.source_value)
        if handler:
            if (
                handler in PROPERTY_HANDLER_REQUIRES_VALUE_MATCH
                and not contains_phrase(raw_value, rule.source_value)
            ):
                continue
            metric = runtime.metrics.get(rule.property_name)
            value = run_many_to_many_handler(
                handler,
                raw_value=raw_value,
                property_name=rule.property_name,
                canonical_unit=(
                    metric.measurability if metric else "millimeters"
                ),
                number_format=(metric.number_format if metric else "integer"),
            )
        elif rule.property_type == "numerical":
            value = _numeric_property(runtime, rule.property_name, raw_value)
        elif contains_phrase(raw_value, rule.source_value):
            value = rule.normalized_property
        else:
            continue
        if value is None and handler != "color_missing":
            continue
        priority = runtime.source_priorities.get(
            (product.source, rule.source_table, "property"), 100
        )
        candidates[rule.property_name].append((
            priority, rule.id, value, rule.source_table, matched_field, raw_value
        ))

    for rule in runtime.price_rules[product.source]:
        raw_value = product.price_fields.get(rule.source_field)
        if raw_value in (None, ""):
            continue
        handler = _rule_handler(runtime, rule.normalized_property, rule.source_value)
        if handler:
            metric = runtime.metrics.get(rule.property_name)
            value = run_many_to_many_handler(
                handler,
                raw_value=raw_value,
                property_name=rule.property_name,
                canonical_unit=(
                    metric.measurability if metric else "millimeters"
                ),
                number_format=(metric.number_format if metric else "integer"),
            )
            if value is None:
                continue
        elif not contains_phrase(raw_value, rule.source_value):
            continue
        elif rule.property_type == "numerical":
            value = _numeric_property(runtime, rule.property_name, raw_value)
        else:
            value = rule.normalized_property
        if value is None:
            continue
        scope = "name" if rule.source_field == "name" else "price"
        priority = runtime.source_priorities.get(
            (product.source, rule.source_table, scope), 100
        )
        candidates[rule.property_name].append((
            priority, rule.id, value, rule.source_table, rule.source_field, raw_value
        ))

    result = {}
    evidence = {}
    for property_name, values in candidates.items():
        values.sort(key=lambda item: (item[0], item[1]))
        priority, _, value, table, field, raw = values[0]
        result[property_name] = value
        evidence[property_name] = {
            "value": _json_value(value), "source_table": table,
            "source_field": field, "raw": str(raw), "priority": priority,
        }
    if product.source == "tt" and result.get("material") in (None, ""):
        if "default_tt_material_pe_pp" in runtime.handlers.values():
            result["material"] = "PE/PP"
            evidence["material"] = {
                "value": "PE/PP", "source_table": "directory_default",
                "source_field": "material", "raw": "",
                "priority": 1000,
            }
    return result, evidence


def apply_manual_properties(runtime, product_key, properties, evidence):
    for property_name, raw_value in runtime.manual_properties.get(
        product_key, {}
    ).items():
        value = (
            _numeric_property(runtime, property_name, raw_value)
            if property_name in runtime.metrics
            else raw_value
        )
        if value in (None, ""):
            continue
        properties[property_name] = value
        evidence[property_name] = {
            "value": _json_value(value),
            "source_table": "analytics_product_manual_property",
            "source_field": "value",
            "raw": str(raw_value),
            "priority": 0,
            "manual": True,
        }
    return properties, evidence


def _phrase_specificity(value):
    normalized = normalize_text(value)
    return len(normalized.split()), len(normalized)


def _phrase_matches(value, expression):
    return any(contains_phrase(value, alternative) for alternative in split_or(expression))


def _condition_matches(runtime, raw_value, expected, field_expression):
    expected_values = split_or(expected)
    dimension_expected = False
    scalar_expected_values = []
    for expected_value in expected_values:
        normalized_expected = normalize_text(expected_value)
        if "x" not in normalized_expected:
            scalar_expected_values.append(expected_value)
            continue
        dimension_expected = True
        expected_dimensions = [
            extract_dimension(expected_value, index) for index in range(3)
        ]
        actual_dimensions = [
            extract_dimension(raw_value, index) for index in range(3)
        ]
        compared = 0
        matched = True
        for index, metric_name in enumerate(("length", "width", "height")):
            wanted = expected_dimensions[index]
            actual = actual_dimensions[index]
            if wanted is None:
                continue
            compared += 1
            metric = runtime.metrics.get(metric_name)
            if actual is None or metric is None or abs(actual - wanted) > metric.tolerance:
                matched = False
                break
        if compared and matched:
            return True
    # A failed compound dimension must never fall through to scalar matching:
    # otherwise 1200x800 incorrectly satisfies 1200x1000 because their first
    # numeric component is the same. Non-dimensional OR alternatives, if any,
    # may still be evaluated by the ordinary logic below.
    if dimension_expected and not scalar_expected_values:
        return False
    values_for_scalar_match = (
        scalar_expected_values if dimension_expected else expected_values
    )
    # Determine a metric from the normalization dictionary for this field.
    metric_name = None
    normalized_fields = {normalize_text(item) for item in split_or(field_expression)}
    for rules in runtime.property_rules.values():
        for rule in rules:
            if any(
                normalize_text(field) in normalized_fields
                for field in split_or(rule.field_text)
            ) and rule.property_type == "numerical":
                metric_name = rule.property_name
                break
        if metric_name:
            break
    if metric_name:
        actual = _numeric_property(runtime, metric_name, raw_value)
        metric = runtime.metrics[metric_name]
        for expected_value in values_for_scalar_match:
            wanted = _numeric_property(runtime, metric_name, expected_value)
            if actual is not None and wanted is not None:
                if abs(actual - wanted) <= metric.tolerance:
                    return True
        return False
    return any(
        contains_phrase(raw_value, expected_value)
        for expected_value in values_for_scalar_match
    )


def _property_classification_rule_matches(runtime, product, rule):
    if not _phrase_matches(product.name, rule.subcategory_value):
        return False, []
    field_groups = split_and(rule.subcategory_type_field_text)
    value_groups = split_and(rule.subcategory_type_value)
    matched = []
    for fields, expected in zip(field_groups, value_groups):
        # For OR fields, unlike left-to-right property extraction, any field may
        # satisfy any expected OR value (e.g. ``Внешний вид//Тип``).
        group_match = None
        for field in split_or(fields):
            raw = product.raw_properties.get(normalize_text(field))
            if raw not in (None, "") and _condition_matches(
                runtime, raw, expected, field
            ):
                group_match = {"field": field, "raw": str(raw), "expected": expected}
                break
        if group_match is None:
            return False, []
        matched.append(group_match)
    return True, matched


def classify_product(runtime, product):
    complete_candidates = []
    partial_subcategory_rules = []

    # A classification_property row is eligible only when both levels match:
    # H (subcategory phrase) AND K/L (property condition).
    for rule in runtime.classification_property[product.source]:
        if not _phrase_matches(product.name, rule.subcategory_value):
            continue
        partial_subcategory_rules.append(rule)
        matches, evidence = _property_classification_rule_matches(
            runtime, product, rule
        )
        if not matches:
            continue
        if "///" in rule.subcategory_type_field_text:
            kind = "composite_property"
        elif any(char.isdigit() for char in rule.subcategory_type_value):
            kind = "numeric_property"
        else:
            kind = "exact_property"
        if _rule_handler(runtime, rule.subcategory_type_value):
            kind = "many_to_many"
        priority = runtime.priorities.get(
            ("subcategory_type", "classification_property", kind), 400
        )
        conditions = 1 + len(split_and(rule.subcategory_type_field_text))
        combined_expression = (
            f"{rule.subcategory_value} {rule.subcategory_type_value}"
        )
        specificity = _phrase_specificity(combined_expression)
        complete_candidates.append((
            priority, conditions, *specificity, -rule.id,
            "classification_property", rule, evidence,
        ))

    # A classification_price row is eligible only when H and K both match in
    # the same row. A long compatibility phrase in H can no longer defeat a
    # complete product rule merely because it contains more tokens.
    for rule in runtime.classification_price[product.source]:
        if not _phrase_matches(product.name, rule.subcategory_value):
            continue
        partial_subcategory_rules.append(rule)
        if not _phrase_matches(product.name, rule.subcategory_type_value):
            continue
        priority = runtime.priorities.get(
            ("subcategory_type", "classification_price", "exact_phrase"), 300
        )
        combined_expression = (
            f"{rule.subcategory_value} {rule.subcategory_type_value}"
        )
        specificity = _phrase_specificity(combined_expression)
        complete_candidates.append((
            priority, 2, *specificity, -rule.id,
            "classification_price", rule,
            [{"field": rule.subcategory_type_field, "raw": product.name,
              "expected": rule.subcategory_type_value}],
        ))

    if not complete_candidates:
        return ClassificationDecision(evidence={
            "reason": (
                "subcategory_type_condition_not_matched"
                if partial_subcategory_rules else "no_subcategory_rule"
            ),
            "partial_rule_ids": [rule.id for rule in partial_subcategory_rules],
        })

    # priority, number of conditions, token count and phrase length determine
    # the business rank. ID is only a stable final ordering key and is not used
    # to hide an ambiguity between equally strong classifications.
    complete_candidates.sort(
        reverse=True,
        key=lambda item: item[:5],
    )
    best = complete_candidates[0]
    tied = [item for item in complete_candidates if item[:4] == best[:4]]
    rule_source = best[-3]
    selected_rule = best[-2]
    type_evidence = best[-1]
    ambiguous = len({
        (
            item[-2].item_type,
            item[-2].category,
            item[-2].subcategory,
            item[-2].subcategory_type,
        )
        for item in tied
    }) > 1

    return ClassificationDecision(
        item_type=selected_rule.item_type,
        category=selected_rule.category,
        subcategory=selected_rule.subcategory,
        subcategory_type=selected_rule.subcategory_type,
        ambiguous=ambiguous,
        evidence={
            "subcategory_rule_id": selected_rule.id,
            "subcategory_rule_source": rule_source,
            "subcategory_phrase": selected_rule.subcategory_value,
            "subcategory_type_rule_id": selected_rule.id,
            "subcategory_type_conditions": type_evidence,
            "full_row_match": True,
        },
    )


def calculate_classification_score(runtime, decision, properties, property_evidence):
    profile = runtime.profile(runtime.classification_profiles, decision)
    if not profile:
        return None, Decimal("0"), Decimal("0"), {
            "reason": "score_profile_not_found"
        }
    available = Decimal("0")
    matched = Decimal("0")
    evidence = {}
    for name, weight in profile["weights"].items():
        value = properties.get(name)
        is_available = value not in (None, "")
        if is_available:
            available += weight
            # A normalized value is considered valid evidence. Classification
            # rules choose the class; score measures quality/completeness of
            # usable evidence inside that class.
            matched += weight
        evidence[name] = {
            "value": _json_value(value), "available": is_available,
            "matched": is_available, "weight": _json_value(weight),
            "source": property_evidence.get(name, {}).get("source_table"),
        }
    # The profile total is the expected evidence. Dividing by the available
    # subset made an incomplete product look 100% classified.
    score = (
        Decimal("0")
        if profile["total"] == 0
        else matched / profile["total"] * 100
    )
    return score, available, matched, evidence


def _format_number(value):
    value = _decimal(value)
    if value is None:
        return ""
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def _plural(number, one, few, many):
    number = int(Decimal(str(number)))
    if number % 100 in range(11, 15):
        return many
    if number % 10 == 1:
        return one
    if number % 10 in (2, 3, 4):
        return few
    return many


MODIFICATION_NO_ADDITIONAL_PROPERTIES = "Без дополнительных характеристик"
MODIFICATION_NOT_DETERMINED = "Не определено автоматически"
MODIFICATION_NOT_DEFINED_REASON = "MODIFICATION_NOT_DEFINED"


def build_modification(runtime, properties, decision):
    profile = runtime.profile(runtime.matching_profiles, decision)
    profile_code = profile["code"] if profile else "MATCH_PROFILE_NOT_FOUND"
    weighted_properties = set(profile["weights"]) if profile else set()
    modification_properties = weighted_properties - {"material", "color"}
    renderable_properties = {
        rule.property_name for rule in runtime.modification_rules
    }
    configured_properties = modification_properties & renderable_properties
    fragments = []
    used = set()
    dimensions = [
        properties.get(name) if name in configured_properties else None
        for name in ("length", "width", "height")
    ]
    if any(value not in (None, "") for value in dimensions):
        if dimensions[0] not in (None, "") and dimensions[1] not in (None, ""):
            present = [_format_number(value) for value in dimensions if value not in (None, "")]
            fragments.append("×".join(present) + " мм")
        else:
            labels = ("Д", "Ш", "В")
            fragments.append(" · ".join(
                f"{label} {_format_number(value)} мм"
                for label, value in zip(labels, dimensions)
                if value not in (None, "")
            ))
        used.update(("length", "width", "height"))

    runner_number = (
        properties.get("runner_number")
        if "runner_number" in configured_properties else None
    )
    wheel_number = (
        properties.get("wheel_number")
        if "wheel_number" in configured_properties else None
    )
    wheel_diameter = (
        properties.get("wheel_diameter")
        if "wheel_diameter" in configured_properties else None
    )
    drain_diameter = (
        properties.get("drain_hole_diameter")
        if "drain_hole_diameter" in configured_properties else None
    )
    if runner_number not in (None, ""):
        used.add("runner_included")
    if wheel_number not in (None, "") or wheel_diameter not in (None, ""):
        used.add("wheel_included")
    for rule in runtime.modification_rules:
        name = rule.property_name
        if name in used or name not in configured_properties:
            continue
        value = properties.get(name)
        if value in (None, ""):
            continue
        fragment = ""
        if name == "runner_number":
            fragment = f"{_format_number(value)} {_plural(value, 'полоз', 'полоза', 'полозьев')}"
            used.add("runner_included")
        elif name == "wheel_number":
            fragment = f"{_format_number(value)} {_plural(value, 'колесо', 'колеса', 'колес')}"
            if wheel_diameter not in (None, ""):
                fragment += f" Ø{_format_number(wheel_diameter)} мм"
                used.add("wheel_diameter")
            used.add("wheel_included")
        elif name == "wheel_diameter":
            fragment = f"колеса Ø{_format_number(value)} мм"
        elif name == "drain_hole_included" and drain_diameter not in (None, ""):
            fragment = f"сливное отверстие Ø{_format_number(drain_diameter)} мм"
            used.add("drain_hole_diameter")
        elif name == "drain_hole_diameter":
            fragment = f"сливное отверстие Ø{_format_number(value)} мм"
        elif rule.value_type == "boolean":
            truthy = normalize_text(value) in {"1", "true", "да", "есть", "включено"}
            fragment = rule.template_true if truthy else rule.template_false
        elif rule.render_rule == "mapped_value":
            mapped = rule.value_map.get(str(value), str(value))
            fragment = (rule.template_value or "{value}").replace("{value}", mapped)
            if name == "support_type":
                normalized_support = normalize_text(value)
                if normalized_support == "ножки":
                    used.add("legs_included")
                elif normalized_support == "колеса":
                    used.add("wheel_included")
                elif normalized_support == "полозья":
                    used.add("runner_included")
        else:
            fragment = (rule.template_value or "{value}").replace(
                "{value}", _format_number(value) if rule.value_type == "numerical" else str(value)
            )
        if fragment:
            fragments.append(fragment)
        used.add(name)
    code_parts = []
    for name in sorted(configured_properties):
        value = properties.get(name)
        if value not in (None, ""):
            code_parts.append(f"{name.upper()}={normalize_text(value)}")
    if fragments:
        modification = " · ".join(dict.fromkeys(fragments))
        code_source = "|".join(code_parts)
        reason = None
    elif profile and not modification_properties:
        modification = MODIFICATION_NO_ADDITIONAL_PROPERTIES
        code_source = f"{profile_code}|NO_ADDITIONAL_PROPERTIES"
        reason = None
    else:
        modification = MODIFICATION_NOT_DETERMINED
        code_source = f"{profile_code}|NOT_DETERMINED"
        reason = MODIFICATION_NOT_DEFINED_REASON
    code = hashlib.sha256(code_source.encode("utf-8")).hexdigest()[:32]
    return modification, code, reason


def _classification_status(runtime, decision, score):
    if not decision.subcategory:
        if (decision.evidence or {}).get("reason") == (
            "subcategory_type_condition_not_matched"
        ):
            return "review", ["SUBCATEGORY_TYPE_NOT_DEFINED"]
        return "unclassified", ["NO_SUBCATEGORY"]
    if decision.ambiguous:
        return "review", ["AMBIGUOUS_CLASSIFICATION"]
    if (
        not decision.subcategory_type
        and normalize_text(decision.subcategory) in runtime.subcategories_with_types
    ):
        return "review", ["SUBCATEGORY_TYPE_NOT_DEFINED"]
    threshold = runtime.threshold("classification_score", score or 0)
    status = threshold.status if threshold else "unclassified"
    reasons = [] if status == "classified" else [
        "LOW_CLASSIFICATION_SCORE" if status == "review" else "UNCLASSIFIED"
    ]
    return status, reasons


def _create_analysis_rows(run, runtime, model, source):
    pending = []
    count = 0
    requested_fields = {
        rule.source_field for rule in runtime.price_rules[source]
        if rule.source_field
    }
    for product in iter_source_products(model, source, requested_fields):
        properties, property_evidence = extract_normalized_properties(runtime, product)
        properties, property_evidence = apply_manual_properties(
            runtime, product.product_key, properties, property_evidence
        )
        decision = classify_product(runtime, product)
        score, available, matched, score_evidence = calculate_classification_score(
            runtime, decision, properties, property_evidence
        )
        status, reasons = _classification_status(runtime, decision, score)
        modification, modification_code, modification_reason = build_modification(
            runtime, properties, decision
        )
        if modification_reason:
            reasons = [*reasons, modification_reason]
            if status == "classified":
                status = "review"
        pending.append(AnalyticsProductAnalysisResult(
            run=run, product_key=product.product_key, source=source,
            product_name=product.name, url=product.url, image=product.image,
            item_type=decision.item_type, category=decision.category,
            subcategory=decision.subcategory,
            subcategory_type=decision.subcategory_type,
            classification_status=status, classification_score=score,
            classification_available_weight=available,
            classification_matched_weight=matched,
            normalized_properties={k: _json_value(v) for k, v in properties.items()},
            classification_evidence={
                "rules": decision.evidence, "properties": property_evidence,
                "score": score_evidence,
            },
            modification=modification, modification_code=modification_code,
            control_reasons=reasons,
        ))
        if len(pending) >= RESULT_BATCH_SIZE:
            AnalyticsProductAnalysisResult.objects.bulk_create(
                pending, batch_size=RESULT_BATCH_SIZE
            )
            count += len(pending)
            pending.clear()
    if pending:
        AnalyticsProductAnalysisResult.objects.bulk_create(
            pending, batch_size=RESULT_BATCH_SIZE
        )
        count += len(pending)
    return count


def _compare_property(runtime, name, left, right):
    if left in (None, "") or right in (None, ""):
        return None
    if left == "__ANY__" or right == "__ANY__":
        return True
    metric = runtime.metrics.get(name)
    if metric:
        left_number = _decimal(left)
        right_number = _decimal(right)
        if left_number is None or right_number is None:
            return False
        return abs(left_number - right_number) <= metric.tolerance
    return normalize_text(left) == normalize_text(right)


def _match_candidate(runtime, base_row, candidate, profile):
    left = base_row.normalized_properties or {}
    right = candidate["normalized_properties"] or {}
    available = Decimal("0")
    matched = Decimal("0")
    evidence = {}
    strict_mismatches = []
    for name, weight in profile["weights"].items():
        strict_threshold = runtime.threshold("matching_property_weight", weight)
        is_strict = bool(
            strict_threshold
            and strict_threshold.auto_action == "require_exact_match"
        )
        left_value = left.get(name)
        right_value = right.get(name)
        result = _compare_property(runtime, name, left_value, right_value)
        missing_base = left_value in (None, "")
        missing_competitor = right_value in (None, "")
        if result is None and not is_strict:
            continue
        if result is None:
            strict_mismatches.append(name)
            evidence[name] = {
                "label": get_match_property_label(name),
                "base": left_value,
                "competitor": right_value,
                "matched": False,
                "weight": _json_value(weight),
                "strict": True,
                "missing_base": missing_base,
                "missing_competitor": missing_competitor,
            }
            continue
        available += weight
        if result:
            matched += weight
        elif is_strict:
            strict_mismatches.append(name)
        evidence[name] = {
            "label": get_match_property_label(name),
            "base": left.get(name), "competitor": right.get(name),
            "matched": result, "weight": _json_value(weight),
            "strict": is_strict,
        }
    score = Decimal("0") if available == 0 else matched / available * 100
    coverage = Decimal("0") if profile["total"] == 0 else available / profile["total"] * 100
    return score, coverage, evidence, strict_mismatches


def _strict_property_reasons(evidence):
    strict_failed = [
        item for item in evidence.values()
        if item.get("strict") and not item.get("matched")
    ]
    reasons = []
    if any(item.get("missing_base") for item in strict_failed):
        reasons.append("STRICT_PROPERTY_MISSING_BASE")
    if any(item.get("missing_competitor") for item in strict_failed):
        reasons.append("STRICT_PROPERTY_MISSING_COMPETITOR")
    if any(
        not item.get("missing_base") and not item.get("missing_competitor")
        for item in strict_failed
    ):
        reasons.append("STRICT_PROPERTY_MISMATCH")
    return reasons


def _threshold_result(runtime, metric, value, allowed_actions):
    threshold = runtime.threshold(metric, value)
    allowed = bool(threshold and threshold.auto_action in allowed_actions)
    return threshold, allowed


def _store_own_assortment_candidates(run, runtime, application):
    """Persist base-to-base evidence for the weighted own-assortment tab."""
    pending = []
    bases = AnalyticsProductAnalysisResult.objects.filter(
        run=run, source="base", classification_status="classified"
    ).order_by("id")
    for base in bases.iterator(chunk_size=100):
        decision = ClassificationDecision(
            item_type=base.item_type, category=base.category,
            subcategory=base.subcategory, subcategory_type=base.subcategory_type,
        )
        profile = runtime.profile(runtime.matching_profiles, decision)
        if not profile:
            continue
        candidates = bases.filter(
            item_type=base.item_type, category=base.category,
            subcategory=base.subcategory, subcategory_type=base.subcategory_type,
        ).exclude(product_key=base.product_key).values(
            "product_key", "normalized_properties"
        ).order_by("product_key")
        for candidate in candidates.iterator(chunk_size=QUERY_CHUNK_SIZE):
            score, coverage, evidence, strict_mismatches = _match_candidate(
                runtime, base, candidate, profile
            )
            score_threshold, score_allowed = _threshold_result(
                runtime, "match_score", score, {"auto_match"}
            )
            coverage_threshold, coverage_allowed = _threshold_result(
                runtime, "match_coverage", coverage, {"auto_match_allowed"}
            )
            pending.append(AnalyticsProductMatchCandidate(
                run=run, application=application,
                product_key_base=base.product_key,
                product_key_competitor=candidate["product_key"],
                competitor_source="base",
                match_score=score, match_coverage=coverage,
                is_eligible=(
                    score_allowed and coverage_allowed and not strict_mismatches
                ),
                threshold_status=(
                    f"score:{getattr(score_threshold, 'status', 'not_configured')};"
                    f"coverage:{getattr(coverage_threshold, 'status', 'not_configured')};"
                    f"strict:{'failed' if strict_mismatches else 'passed'}"
                ),
                control_reasons=(
                    ([] if score_allowed else ["LOW_MATCH_SCORE"])
                    + ([] if coverage_allowed else ["LOW_MATCH_COVERAGE"])
                    + _strict_property_reasons(evidence)
                ),
                match_evidence=evidence,
            ))
            if len(pending) >= RESULT_BATCH_SIZE:
                AnalyticsProductMatchCandidate.objects.bulk_create(
                    pending, batch_size=RESULT_BATCH_SIZE
                )
                pending.clear()
    if pending:
        AnalyticsProductMatchCandidate.objects.bulk_create(
            pending, batch_size=RESULT_BATCH_SIZE
        )


def _apply_matching(run, runtime, *, application=None):
    AnalyticsProductAnalysisResult.objects.filter(run=run, source="base").update(
        best_match_product_key=None,
        best_match_name="",
        match_score=None,
        match_coverage=None,
        second_match_product_key=None,
        second_match_name="",
        second_match_score=None,
        match_gap=None,
        match_status="",
        match_evidence={},
    )
    bases = (
        AnalyticsProductAnalysisResult.objects.filter(
            run=run, source="base", classification_status="classified"
        ).order_by("id")
    )
    AnalyticsProductMatchCandidate.objects.filter(
        run=run, application=application
    ).delete()
    updates = []
    candidate_rows = []
    matched_count = 0
    for base in bases.iterator(chunk_size=100):
        decision = ClassificationDecision(
            item_type=base.item_type, category=base.category,
            subcategory=base.subcategory, subcategory_type=base.subcategory_type,
        )
        profile = runtime.profile(runtime.matching_profiles, decision)
        if not profile:
            base.match_status = "no_match"
            base.control_reasons = [*base.control_reasons, "MATCH_PROFILE_NOT_FOUND"]
            updates.append(base)
            continue
        candidates = (
            AnalyticsProductAnalysisResult.objects.filter(
                run=run, classification_status="classified",
                item_type=base.item_type, category=base.category,
                subcategory=base.subcategory, subcategory_type=base.subcategory_type,
            ).exclude(source="base").values(
                "product_key", "product_name", "source", "normalized_properties"
            ).order_by("source", "product_key")
        )
        best = []
        best_eligible = []
        eligible_count = 0
        for candidate in candidates.iterator(chunk_size=QUERY_CHUNK_SIZE):
            score, coverage, evidence, strict_mismatches = _match_candidate(
                runtime, base, candidate, profile
            )
            score_threshold, score_allowed = _threshold_result(
                runtime, "match_score", score, {"auto_match"}
            )
            coverage_threshold, coverage_allowed = _threshold_result(
                runtime, "match_coverage", coverage, {"auto_match_allowed"}
            )
            reasons = []
            if not score_allowed:
                reasons.append("LOW_MATCH_SCORE")
            if not coverage_allowed:
                reasons.append("LOW_MATCH_COVERAGE")
            reasons.extend(_strict_property_reasons(evidence))
            eligible = (
                score_allowed and coverage_allowed and not strict_mismatches
            )
            if eligible:
                eligible_count += 1
            candidate_rows.append(AnalyticsProductMatchCandidate(
                run=run,
                application=application,
                product_key_base=base.product_key,
                product_key_competitor=candidate["product_key"],
                competitor_source=candidate["source"],
                match_score=score,
                match_coverage=coverage,
                is_eligible=eligible,
                threshold_status=(
                    f"score:{getattr(score_threshold, 'status', 'not_configured')};"
                    f"coverage:{getattr(coverage_threshold, 'status', 'not_configured')};"
                    f"strict:{'failed' if strict_mismatches else 'passed'}"
                ),
                control_reasons=reasons,
                match_evidence=evidence,
            ))
            if len(candidate_rows) >= RESULT_BATCH_SIZE:
                AnalyticsProductMatchCandidate.objects.bulk_create(
                    candidate_rows, batch_size=RESULT_BATCH_SIZE
                )
                candidate_rows.clear()
            item = (score, coverage, -candidate["product_key"], candidate, evidence)
            best.append(item)
            best.sort(reverse=True, key=lambda value: value[:3])
            if len(best) > 2:
                best.pop()
            if eligible:
                best_eligible.append(item)
                best_eligible.sort(reverse=True, key=lambda value: value[:3])
                if len(best_eligible) > 2:
                    best_eligible.pop()
        if not best:
            base.match_status = "no_match"
            base.control_reasons = [*base.control_reasons, "NO_MATCH"]
            updates.append(base)
            continue
        summary_candidates = best_eligible or best
        first = summary_candidates[0]
        second = summary_candidates[1] if len(summary_candidates) > 1 else None
        gap = first[0] - second[0] if second else Decimal("100")
        base.best_match_product_key = first[3]["product_key"]
        base.best_match_name = first[3]["product_name"]
        base.match_score = first[0]
        base.match_coverage = first[1]
        base.match_evidence = first[4]
        base.match_gap = gap
        if second:
            base.second_match_product_key = second[3]["product_key"]
            base.second_match_name = second[3]["product_name"]
            base.second_match_score = second[0]
        reasons = list(base.control_reasons)
        score_threshold, score_allowed = _threshold_result(
            runtime, "match_score", first[0], {"auto_match"}
        )
        coverage_threshold, coverage_allowed = _threshold_result(
            runtime, "match_coverage", first[1], {"auto_match_allowed"}
        )
        if not score_allowed:
            reasons.append("LOW_MATCH_SCORE")
        if not coverage_allowed:
            reasons.append("LOW_MATCH_COVERAGE")
        reasons.extend(_strict_property_reasons(first[4]))
        gap_threshold, gap_clear = _threshold_result(
            runtime, "match_gap", gap, {"auto_match_allowed"}
        )
        if not gap_clear:
            reasons.append("AMBIGUOUS_MATCH")
        # Gap remains an explanation of close candidates. In a many-to-many
        # result it must not disqualify independently eligible analogues.
        base.match_status = "matched" if eligible_count else "review"
        base.control_reasons = reasons
        matched_count += eligible_count
        updates.append(base)
        if len(updates) >= RESULT_BATCH_SIZE:
            AnalyticsProductAnalysisResult.objects.bulk_update(
                updates,
                fields=(
                    "best_match_product_key", "best_match_name", "match_score",
                    "match_coverage", "second_match_product_key",
                    "second_match_name", "second_match_score", "match_gap",
                    "match_status", "match_evidence", "control_reasons",
                ),
                batch_size=RESULT_BATCH_SIZE,
            )
            updates.clear()
    if candidate_rows:
        AnalyticsProductMatchCandidate.objects.bulk_create(
            candidate_rows, batch_size=RESULT_BATCH_SIZE
        )
    if updates:
        AnalyticsProductAnalysisResult.objects.bulk_update(
            updates,
            fields=(
                "best_match_product_key", "best_match_name", "match_score",
                "match_coverage", "second_match_product_key",
                "second_match_name", "second_match_score", "match_gap",
                "match_status", "match_evidence", "control_reasons",
            ),
            batch_size=RESULT_BATCH_SIZE,
        )
    if application is not None:
        _store_own_assortment_candidates(run, runtime, application)
    return matched_count


def _set_run(run, **values):
    for field, value in values.items():
        setattr(run, field, value)
    run.save(update_fields=tuple(values))


def _process_analytics_products_locked(run_id):
    run = AnalyticsProductProcessingRun.objects.get(pk=run_id)
    _set_run(
        run, status=AnalyticsProductProcessingRun.STATUS_RUNNING,
        current_step="loading_directory", started_at=timezone.now(), error_text="",
    )
    from datasets.services.iprice_runtime import publish_iprice_update
    publish_iprice_update(
        "product_classification_started",
        run_id=run.id,
        directory_load_id=run.directory_load_id,
        status=run.status,
        current_step=run.current_step,
    )
    try:
        runtime = DirectoryRuntime()
        with transaction.atomic():
            AnalyticsProductAnalysisResult.objects.filter(run=run).delete()
        source_counts = {}
        unknown_sources = [source for source in runtime.sources if source not in SOURCE_MODELS]
        if unknown_sources:
            raise ValueError(
                "Не поддерживаются источники directory: " + ", ".join(unknown_sources)
            )
        if "base" not in runtime.sources:
            raise ValueError(
                "В classification_price/classification_property отсутствует source=base"
            )
        for source in runtime.sources:
            _set_run(run, current_step=f"classifying_{source}")
            publish_iprice_update(
                "product_classification_progress",
                run_id=run.id, status=run.status, current_step=run.current_step,
            )
            source_counts[source] = _create_analysis_rows(
                run, runtime, SOURCE_MODELS[source], source
            )
        _set_run(run, current_step="matching")
        publish_iprice_update(
            "product_classification_progress",
            run_id=run.id, status=run.status, current_step=run.current_step,
        )
        matched_count = _apply_matching(run, runtime)
        _set_run(run, current_step="building_export")
        publish_iprice_update(
            "product_classification_progress",
            run_id=run.id, status=run.status, current_step=run.current_step,
        )
        result = {
            "run_id": run.id,
            "source_products": source_counts,
            "base_products": source_counts.get("base", 0),
            "auto_matches": matched_count,
            "export_ready": False,
        }
        # The run becomes successful only after the atomically replaced export
        # is on disk. Until then the UI must keep the download disabled.
        finished_at = timezone.now()
        from datasets.services.parsers.product_url_export import (
            save_product_url_control_excel,
        )
        export_path = save_product_url_control_excel(
            run_id=run.id,
            summary_status=AnalyticsProductProcessingRun.STATUS_SUCCESS,
            summary_finished_at=finished_at,
        )
        result["export_path"] = str(export_path)
        result["export_ready"] = True
        _set_run(
            run,
            status=AnalyticsProductProcessingRun.STATUS_SUCCESS,
            current_step="completed",
            finished_at=finished_at,
            result=result,
        )
        publish_iprice_update(
            "product_classification_completed",
            run_id=run.id,
            directory_load_id=run.directory_load_id,
            status=run.status,
            current_step=run.current_step,
            result=result,
        )
        return result
    except Exception as exc:
        logger.exception("Analytics product processing failed: run_id=%s", run_id)
        _set_run(
            run, status=AnalyticsProductProcessingRun.STATUS_FAILED,
            current_step="failed", finished_at=timezone.now(), error_text=str(exc),
        )
        publish_iprice_update(
            "product_classification_failed",
            run_id=run.id,
            directory_load_id=run.directory_load_id,
            status=run.status,
            current_step=run.current_step,
            error=str(exc),
        )
        raise


def process_analytics_products(run_id):
    with analytics_product_operation_lock():
        return _process_analytics_products_locked(run_id)
