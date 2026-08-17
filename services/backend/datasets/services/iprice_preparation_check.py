from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db.models import Exists, Max, OuterRef, Subquery
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from datasets.models import (
    BaseProductPrice,
    DepartureDiscount,
    Nomenclature,
    NomenclaturePrice,
    ParserPrefix,
    ParserProductClassification,
    ParserProductMatch,
    ParserProductUrl,
    ProductCost,
    TransportCost,
    IPriceCalculationConfig,
    AnalyticsProductClassificationApplication,
    AnalyticsProductMatchCandidate,
)
from datasets.services.parsers.analytics_product_processor import (
    MODIFICATION_NOT_DETERMINED,
)
ERROR = "ERROR"
WARNING = "WARNING"

MATCH_CLASSIFICATION_FIELDS = (
    "item_type",
    "category",
    "subcategory",
    "subcategory_type",
)



# ============================================================
# COMMON HELPERS
# ============================================================


def is_blank(value):
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    return False


def normalize_text(value):
    if value is None:
        return None

    value = str(value).strip()

    return value or None


def split_regions(value):
    """
    Пример:

    "Москва;Ставрово"
        ->
    ["Москва", "Ставрово"]
    """

    value = normalize_text(value)

    if not value:
        return []

    return [
        part.strip()
        for part in value.split(";")
        if part.strip()
    ]


def clean_decimal(value):
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

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


def add_issue(
    issues,
    level,
    error_code,
    business_key,
    message,
    **extra,
):
    issue = {
        "level": level,
        "error_code": error_code,
        "business_key": str(
            business_key
            if business_key is not None
            else ""
        ),
        "message": message,
    }

    issue.update(extra)

    issues.append(issue)


def route_requires_transport(
    departure,
    arrival,
):
    """
    Если производство совпадает с регионом прибытия,
    транспортные расходы равны 0 и запись transport_cost
    не требуется.
    """

    departure = normalize_text(departure)
    arrival = normalize_text(arrival)

    if not departure or not arrival:
        return False

    return departure.casefold() != arrival.casefold()


def normalized_pair(
    departure,
    arrival,
):
    departure = normalize_text(departure)
    arrival = normalize_text(arrival)

    if not departure or not arrival:
        return None

    return (
        departure.casefold(),
        arrival.casefold(),
    )


# ============================================================
# 1. PARSER PRODUCT CLASSIFICATION
# ============================================================


def check_classification():
    issues = []

    rows = list(
        ParserProductClassification.objects.filter(
            status=ParserProductClassification.STATUS_ACTIVE,
        ).values(
            "product_key",
            "category",
            "subcategory",
            "subcategory_type",
            "material",
            "color",
            "modification",
            "item_type",
        )
    )

    if not rows:
        add_issue(
            issues,
            ERROR,
            "TABLE_EMPTY",
            "",
            (
                "Нет активных строк "
                "parser_product_classification"
            ),
        )

        return rows, issues

    product_keys = {
        row["product_key"]
        for row in rows
    }

    urls = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=product_keys,
            )
            .values(
                "id",
                "source",
                "status",
            )
        )
    }

    # --------------------------------------------------------
    # Обычные обязательные текстовые поля
    # --------------------------------------------------------

    required_fields = (
        "category",
        "subcategory",
        "subcategory_type",
        "material",
        "color",
        "modification",
    )

    # --------------------------------------------------------
    # Допустимые типы товара
    # --------------------------------------------------------

    allowed_item_types = {
        ParserProductClassification.ITEM_TYPE_PRODUCT,
        ParserProductClassification.ITEM_TYPE_COMPONENT,
    }

    for row in rows:
        product_key = row[
            "product_key"
        ]

        url_row = urls.get(
            product_key
        )

        # ----------------------------------------------------
        # Проверка существования product_key
        # в ParserProductUrl
        # ----------------------------------------------------

        if url_row is None:
            add_issue(
                issues,
                ERROR,
                "PRODUCT_KEY_NOT_FOUND",
                product_key,
                (
                    "product_key отсутствует "
                    "в parser_product_url"
                ),
                product_key=product_key,
            )

        # ----------------------------------------------------
        # Проверка активности URL
        # ----------------------------------------------------

        elif (
            url_row["status"]
            != ParserProductUrl.STATUS_ACTIVE
        ):
            add_issue(
                issues,
                ERROR,
                "PRODUCT_URL_INACTIVE",
                product_key,
                (
                    "product_key существует в "
                    "parser_product_url, но status != active"
                ),
                product_key=product_key,
                source=url_row["source"],
            )

        # ----------------------------------------------------
        # Проверка обязательных текстовых полей
        # ----------------------------------------------------

        for field_name in required_fields:
            if is_blank(
                row[field_name]
            ):
                add_issue(
                    issues,
                    ERROR,
                    "CLASSIFICATION_FIELD_EMPTY",
                    product_key,
                    (
                        "Не заполнено обязательное поле "
                        f"{field_name}"
                    ),
                    product_key=product_key,
                    field=field_name,
                )

        if row["modification"] == MODIFICATION_NOT_DETERMINED:
            add_issue(
                issues,
                WARNING,
                "MODIFICATION_NOT_DEFINED",
                product_key,
                "Модификация не определена автоматически",
                product_key=product_key,
                field="modification",
            )

        # ----------------------------------------------------
        # Проверка item_type
        #
        # Допустимы только:
        # product
        # component
        # ----------------------------------------------------

        item_type = row[
            "item_type"
        ]

        if item_type not in allowed_item_types:
            add_issue(
                issues,
                ERROR,
                "CLASSIFICATION_ITEM_TYPE_INVALID",
                product_key,
                (
                    "Поле item_type должно содержать "
                    "одно из значений: "
                    "product или component"
                ),
                product_key=product_key,
                item_type=item_type,
            )

    return rows, issues


# ============================================================
# 2. PARSER PRODUCT MATCH
# ============================================================


def check_matches(
    active_classification_keys,
):
    issues = []

    application = AnalyticsProductClassificationApplication.objects.select_related(
        "run"
    ).order_by("-date_add", "-id").first()
    if application is None and active_classification_keys:
        add_issue(
            issues, ERROR, "PRODUCT_CONTROL_APPLICATION_MISSING", "",
            "Активная классификация не связана с применённым результатом Product Control",
        )
    eligible_candidates = AnalyticsProductMatchCandidate.objects.none()
    if application is not None:
        eligible_candidates = AnalyticsProductMatchCandidate.objects.filter(
            application=application, is_eligible=True,
            product_key_base__in=active_classification_keys,
            product_key_competitor__in=active_classification_keys,
        ).exclude(competitor_source="base")

    active_match_for_candidate = ParserProductMatch.objects.filter(
        status=ParserProductMatch.STATUS_ACTIVE,
        product_key_base=OuterRef("product_key_base"),
        product_key_competitor=OuterRef("product_key_competitor"),
    )
    for candidate in eligible_candidates.annotate(
        has_active_match=Exists(active_match_for_candidate)
    ).filter(has_active_match=False).values(
        "product_key_base", "product_key_competitor"
    ).iterator(chunk_size=500):
        base_key = candidate["product_key_base"]
        competitor_key = candidate["product_key_competitor"]
        add_issue(
            issues,
            ERROR,
            "MATCH_EXPECTED_PAIR_MISSING",
            f"{base_key}->{competitor_key}",
            "Отсутствует активная связь, ожидаемая по классификации товаров",
            product_key_base=base_key,
            product_key_competitor=competitor_key,
        )

    weighted_for_match = eligible_candidates.filter(
        product_key_base=OuterRef("product_key_base"),
        product_key_competitor=OuterRef("product_key_competitor"),
    )
    rows = list(
        ParserProductMatch.objects.filter(status=ParserProductMatch.STATUS_ACTIVE)
        .annotate(
            weighted_score=Subquery(weighted_for_match.values("match_score")[:1]),
            weighted_coverage=Subquery(
                weighted_for_match.values("match_coverage")[:1]
            ),
            weighted_evidence=Subquery(
                weighted_for_match.values("match_evidence")[:1]
            ),
            weighted_exists=Exists(weighted_for_match),
        ).values(
            "product_key_base",
            "product_key_competitor",
            "match_type",
            "weighted_score",
            "weighted_coverage",
            "weighted_evidence",
            "weighted_exists",
        )
    )

    if not rows and eligible_candidates.exists():
        add_issue(
            issues,
            ERROR,
            "TABLE_EMPTY",
            "",
            (
                "Нет активных строк "
                "parser_product_match"
            ),
        )

    for row in rows:
        if row["weighted_exists"]:
            continue
        base_key = row["product_key_base"]
        competitor_key = row["product_key_competitor"]
        add_issue(
            issues,
            ERROR,
            "MATCH_UNEXPECTED_ACTIVE_PAIR",
            f"{base_key}->{competitor_key}",
            (
                "Активная связь не входит в прошедший "
                "весовые пороги результат Product Control"
            ),
            product_key_base=base_key,
            product_key_competitor=(
                competitor_key
            ),
        )

    all_keys = set()

    for row in rows:
        all_keys.add(
            row["product_key_base"]
        )
        all_keys.add(
            row["product_key_competitor"]
        )

    urls = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(id__in=all_keys)
            .values(
                "id",
                "source",
                "prefix",
                "status",
            )
        )
    }

    classifications = {
        row["product_key"]: row
        for row in (
            ParserProductClassification.objects
            .filter(
                product_key__in=all_keys,
                status=(
                    ParserProductClassification
                    .STATUS_ACTIVE
                ),
            )
            .values(
                "product_key",
                *MATCH_CLASSIFICATION_FIELDS,
            )
        )
    }

    matched_competitor_keys = set()

    for row in rows:
        base_key = row["product_key_base"]
        competitor_key = (
            row["product_key_competitor"]
        )

        business_key = (
            f"{base_key}->{competitor_key}"
        )
        if not row["weighted_exists"]:
            add_issue(
                issues, ERROR, "MATCH_WEIGHTED_RESULT_MISSING", business_key,
                "Для активной связи отсутствует подходящий весовой результат Product Control",
                product_key_base=base_key, product_key_competitor=competitor_key,
            )
        elif not row["weighted_evidence"]:
            add_issue(
                issues, WARNING, "MATCH_EVIDENCE_EMPTY", business_key,
                "Для активной связи отсутствует детализация сравнения свойств",
            )

        base_classification = (
            classifications.get(base_key)
        )
        competitor_classification = (
            classifications.get(competitor_key)
        )

        if (
            base_classification is not None
            and competitor_classification
            is not None
        ):
            base_signature = tuple(
                normalize_text(base_classification.get(field))
                for field in MATCH_CLASSIFICATION_FIELDS
            )
            competitor_signature = tuple(
                normalize_text(competitor_classification.get(field))
                for field in MATCH_CLASSIFICATION_FIELDS
            )

            if (
                base_signature is not None
                and competitor_signature is not None
                and base_signature
                != competitor_signature
            ):
                add_issue(
                    issues,
                    ERROR,
                    "MATCH_CLASSIFICATION_MISMATCH",
                    business_key,
                    (
                        "Иерархия классификации нашего товара "
                        "и конкурента не совпадает"
                    ),
                    product_key_base=base_key,
                    product_key_competitor=(
                        competitor_key
                    ),
                )

        if (
            row["match_type"]
            != ParserProductMatch.MATCH_TYPE_AUTO
        ):
            add_issue(
                issues,
                WARNING,
                "MATCH_TYPE_NOT_AUTO",
                business_key,
                (
                    "Активная связь не помечена как "
                    "автоматически сформированная"
                ),
            )

        if base_key == competitor_key:
            add_issue(
                issues,
                ERROR,
                "MATCH_SELF_REFERENCE",
                business_key,
                (
                    "product_key_base равен "
                    "product_key_competitor"
                ),
            )

        # ----------------------------------------------------
        # Base
        # ----------------------------------------------------

        base_url = urls.get(base_key)

        if base_url is None:
            add_issue(
                issues,
                ERROR,
                "BASE_PRODUCT_NOT_FOUND",
                base_key,
                (
                    "product_key_base отсутствует "
                    "в parser_product_url"
                ),
            )

        else:
            if base_url["source"] != "base":
                add_issue(
                    issues,
                    ERROR,
                    "BASE_WRONG_SOURCE",
                    base_key,
                    (
                        f"product_key_base имеет "
                        f"source={base_url['source']}, "
                        f"ожидался source=base"
                    ),
                )

            if (
                base_url["status"]
                != ParserProductUrl.STATUS_ACTIVE
            ):
                add_issue(
                    issues,
                    ERROR,
                    "BASE_PRODUCT_INACTIVE",
                    base_key,
                    (
                        "product_key_base существует, "
                        "но неактивен"
                    ),
                )

        # ----------------------------------------------------
        # Competitor
        # ----------------------------------------------------

        competitor_url = urls.get(
            competitor_key
        )

        if competitor_url is None:
            add_issue(
                issues,
                ERROR,
                "COMPETITOR_PRODUCT_NOT_FOUND",
                competitor_key,
                (
                    "product_key_competitor "
                    "отсутствует в parser_product_url"
                ),
            )

        else:
            if competitor_url["source"] == "base":
                add_issue(
                    issues,
                    ERROR,
                    "COMPETITOR_IS_BASE",
                    competitor_key,
                    (
                        "product_key_competitor "
                        "относится к source=base"
                    ),
                )

            if (
                competitor_url["status"]
                != ParserProductUrl.STATUS_ACTIVE
            ):
                add_issue(
                    issues,
                    ERROR,
                    "COMPETITOR_INACTIVE",
                    competitor_key,
                    (
                        "product_key_competitor "
                        "неактивен"
                    ),
                )

            if is_blank(
                competitor_url["prefix"]
            ):
                add_issue(
                    issues,
                    ERROR,
                    "COMPETITOR_PREFIX_EMPTY",
                    competitor_key,
                    (
                        "Для competitor product_key "
                        "не заполнен prefix "
                        "в parser_product_url"
                    ),
                    source=competitor_url[
                        "source"
                    ],
                )

        # ----------------------------------------------------
        # Classification membership
        # ----------------------------------------------------

        if (
            base_key
            not in active_classification_keys
        ):
            add_issue(
                issues,
                ERROR,
                "BASE_NOT_IN_CLASSIFICATION",
                base_key,
                (
                    "product_key_base отсутствует "
                    "в active classification"
                ),
            )

        if (
            competitor_key
            not in active_classification_keys
        ):
            add_issue(
                issues,
                ERROR,
                "COMPETITOR_NOT_IN_CLASSIFICATION",
                competitor_key,
                (
                    "product_key_competitor отсутствует "
                    "в active classification"
                ),
            )

        matched_competitor_keys.add(
            competitor_key
        )

    return rows, issues


# ============================================================
# 3. TRANSPORT COST
# ============================================================


def check_transport_cost():
    issues = []

    rows = list(
        TransportCost.objects
        .filter(
            is_active=True,
        )
        .values(
            "id",
            "departure",
            "arrival",
            "cost",
            "is_active",
            "date_add",
        )
    )

    if not rows:
        add_issue(
            issues,
            ERROR,
            "ACTIVE_TABLE_EMPTY",
            "",
            "Нет активных строк transport_cost",
        )

        return rows, issues

    route_counts = Counter(
        normalized_pair(
            row["departure"],
            row["arrival"],
        )
        for row in rows
        if normalized_pair(
            row["departure"],
            row["arrival"],
        )
    )

    for route, count in route_counts.items():
        if count <= 1:
            continue

        departure, arrival = route

        add_issue(
            issues,
            ERROR,
            "ACTIVE_TRANSPORT_DUPLICATE",
            f"{departure}:{arrival}",
            (
                "Найдено несколько активных строк "
                f"transport_cost для маршрута "
                f"{departure} -> {arrival}: {count}"
            ),
            departure=departure,
            arrival=arrival,
            count=count,
        )


    for row in rows:
        row_id = row["id"]

        departure = normalize_text(
            row["departure"]
        )

        arrival = normalize_text(
            row["arrival"]
        )

        cost = row["cost"]

        # ----------------------------------------------------
        # Обязательные поля
        # ----------------------------------------------------

        if not departure:
            add_issue(
                issues,
                ERROR,
                "DEPARTURE_EMPTY",
                row_id,
                "Не заполнен departure",
            )

        if not arrival:
            add_issue(
                issues,
                ERROR,
                "ARRIVAL_EMPTY",
                row_id,
                "Не заполнен arrival",
            )

        if cost is None:
            add_issue(
                issues,
                ERROR,
                "COST_EMPTY",
                row_id,
                "Не заполнена стоимость перевозки",
            )

        # Если одного из регионов или стоимости нет,
        # следующие проверки по маршруту выполнять нельзя.
        if (
            not departure
            or not arrival
            or cost is None
        ):
            continue

        # ----------------------------------------------------
        # Определяем, совпадают ли регионы
        # ----------------------------------------------------

        same_region = (
            departure.casefold()
            == arrival.casefold()
        )

        # ----------------------------------------------------
        # Правило 1:
        #
        # departure == arrival
        #
        # транспортные расходы должны быть ровно 0.
        #
        # Например:
        # Москва -> Москва = 0
        # Азов -> Азов = 0
        # ----------------------------------------------------

        if same_region:
            if cost != 0:
                add_issue(
                    issues,
                    ERROR,
                    "SAME_REGION_COST_NOT_ZERO",
                    row_id,
                    (
                        f"departure={departure} и "
                        f"arrival={arrival} совпадают, "
                        f"поэтому cost должен быть 0, "
                        f"получено {cost}"
                    ),
                    departure=departure,
                    arrival=arrival,
                    cost=cost,
                )

            # Для одинаковых регионов других проверок
            # стоимости не требуется.
            continue

        # ----------------------------------------------------
        # Правило 2:
        #
        # departure != arrival
        #
        # стоимость перевозки должна быть строго > 0.
        #
        # Например:
        # Азов -> Москва = 54166.66
        #
        # Нельзя:
        # Азов -> Москва = 0
        # Азов -> Москва = -100
        # ----------------------------------------------------

        if cost <= 0:
            add_issue(
                issues,
                ERROR,
                "TRANSPORT_COST_NOT_POSITIVE",
                row_id,
                (
                    f"Для маршрута "
                    f"{departure} -> {arrival} "
                    f"стоимость перевозки должна быть > 0, "
                    f"получено {cost}"
                ),
                departure=departure,
                arrival=arrival,
                cost=cost,
            )

    return rows, issues

# ============================================================
# 4. PARSER PREFIX
# ============================================================


def check_prefixes(
    known_regions,
):
    issues = []

    rows = list(
        ParserPrefix.objects.values(
            "id",
            "source",
            "prefix",
            "shipp_region",
        )
    )

    if not rows:
        add_issue(
            issues,
            ERROR,
            "TABLE_EMPTY",
            "",
            "parser_prefix пустая",
        )

        return rows, issues

    existing_sources = set(
        ParserProductUrl.objects
        .values_list(
            "source",
            flat=True,
        )
        .distinct()
    )

    normalized_known_regions = {
        region.casefold()
        for region in known_regions
        if region
    }

    for row in rows:
        row_id = row["id"]

        source = normalize_text(
            row["source"]
        )

        prefix = normalize_text(
            row["prefix"]
        )

        regions = split_regions(
            row["shipp_region"]
        )

        if not source:
            add_issue(
                issues,
                ERROR,
                "SOURCE_EMPTY",
                row_id,
                "Не заполнен source",
            )

        elif source not in existing_sources:
            add_issue(
                issues,
                WARNING,
                "SOURCE_NOT_USED",
                row_id,
                (
                    f"source={source} "
                    "не найден в parser_product_url"
                ),
            )

        if not prefix:
            add_issue(
                issues,
                ERROR,
                "PREFIX_EMPTY",
                row_id,
                "Не заполнен prefix",
            )

        if not regions:
            add_issue(
                issues,
                ERROR,
                "SHIPP_REGION_EMPTY",
                row_id,
                "Не заполнен shipp_region",
            )

            continue

        for region in regions:
            if (
                region.casefold()
                not in normalized_known_regions
            ):
                add_issue(
                    issues,
                    ERROR,
                    "SHIPP_REGION_UNKNOWN",
                    (
                        f"{source}:"
                        f"{prefix}:"
                        f"{region}"
                    ),
                    (
                        f"Регион {region} "
                        "не найден среди известных "
                        "регионов transport_cost"
                    ),
                    source=source,
                    prefix=prefix,
                    shipp_region=region,
                )

    return rows, issues


# ============================================================
# 5. DEPARTURE DISCOUNT
# ============================================================


def check_departure_discount(
    active_classification_keys,
    transport_departures,
):
    issues = []

    rows = list(
        DepartureDiscount.objects
        .filter(
            is_active=True,
        )
        .values(
            "id",
            "product_key",
            "departure",
            "arrival",
            "distr",
            "distr_1",
            "small",
            "medium",
            "large",
            "is_active",
            "date_add",
        )
    )

    if not rows:
        add_issue(
            issues,
            ERROR,
            "ACTIVE_TABLE_EMPTY",
            "",
            "Нет активных строк departure_discount",
        )

        return rows, issues

    discount_counts = Counter(
        (
            row["product_key"],
            normalize_text(
                row["departure"]
            ).casefold(),
            normalize_text(
                row["arrival"]
            ).casefold(),
        )
        for row in rows
        if normalize_text(
            row["departure"]
        )
    )

    for key, count in discount_counts.items():
        if count <= 1:
            continue

        product_key, departure, arrival = key

        add_issue(
            issues,
            ERROR,
            "ACTIVE_DISCOUNT_DUPLICATE",
            f"{product_key}:{departure}",
            (
                "Найдено несколько активных строк "
                "departure_discount для "
                f"product_key={product_key}, "
                f"departure={departure}, "
                f"arrival={arrival}: {count}"
            ),
            product_key=product_key,
            departure=departure,
            arrival=arrival,
            count=count,
        )

    product_keys = {
        row["product_key"]
        for row in rows
    }

    urls = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(id__in=product_keys)
            .values(
                "id",
                "source",
                "status",
            )
        )
    }

    normalized_departures = {
        departure.casefold()
        for departure in transport_departures
        if departure
    }

    discount_fields = (
        "distr",
        "distr_1",
        "small",
        "medium",
        "large",
    )

    for row in rows:
        product_key = row["product_key"]

        departure = normalize_text(
            row["departure"]
        )

        url_row = urls.get(
            product_key
        )

        if url_row is None:
            add_issue(
                issues,
                ERROR,
                "PRODUCT_KEY_NOT_FOUND",
                product_key,
                (
                    "product_key отсутствует "
                    "в parser_product_url"
                ),
            )

        else:
            if url_row["source"] != "base":
                add_issue(
                    issues,
                    ERROR,
                    "PRODUCT_NOT_BASE",
                    product_key,
                    (
                        f"source={url_row['source']}, "
                        "ожидался source=base"
                    ),
                )

            if (
                url_row["status"]
                != ParserProductUrl.STATUS_ACTIVE
            ):
                add_issue(
                    issues,
                    ERROR,
                    "PRODUCT_INACTIVE",
                    product_key,
                    "Base product неактивен",
                )

        if (
            product_key
            not in active_classification_keys
        ):
            add_issue(
                issues,
                ERROR,
                "PRODUCT_NOT_IN_CLASSIFICATION",
                product_key,
                (
                    "product_key отсутствует "
                    "в active classification"
                ),
            )

        if not departure:
            add_issue(
                issues,
                ERROR,
                "DEPARTURE_EMPTY",
                product_key,
                "Не заполнен departure",
            )

        elif (
            departure.casefold()
            not in normalized_departures
        ):
            add_issue(
                issues,
                ERROR,
                "DEPARTURE_NOT_IN_TRANSPORT",
                f"{product_key}:{departure}",
                (
                    f"departure={departure} "
                    "не найден среди "
                    "transport_cost.departure"
                ),
                product_key=product_key,
                departure=departure,
            )

        for field_name in discount_fields:
            value = row[field_name]

            if value is None:
                add_issue(
                    issues,
                    ERROR,
                    "DISCOUNT_EMPTY",
                    f"{product_key}:{departure}",
                    (
                        f"Не заполнено поле "
                        f"{field_name}"
                    ),
                    product_key=product_key,
                    departure=departure,
                    field=field_name,
                )

                continue

            if not (
                Decimal("0")
                <= value
                < Decimal("1")
            ):
                add_issue(
                    issues,
                    ERROR,
                    "DISCOUNT_INVALID",
                    f"{product_key}:{departure}",
                    (
                        f"{field_name}={value}; "
                        "скидка должна быть "
                        ">= 0 и < 1"
                    ),
                    product_key=product_key,
                    departure=departure,
                    field=field_name,
                )

    return rows, issues


# ============================================================
# 6. CURRENT BASE PRODUCT -> CODE_1C
# ============================================================


def get_current_base_codes(
    product_keys,
):
    """
    Возвращает:
        {
            product_key: code_1c
        }

    Берем наиболее свежую запись BaseProductPrice
    по date_add, при одинаковом date_add — max id.
    """

    issues = []

    if not product_keys:
        return {}, issues

    rows = (
        BaseProductPrice.objects
        .filter(
            product_key__in=product_keys,
        )
        .order_by(
            "product_key",
            "-date_add",
            "-id",
        )
        .values(
            "id",
            "product_key",
            "code_1c",
            "date_add",
        )
    )

    result = {}

    for row in rows:
        product_key = row["product_key"]

        if product_key in result:
            continue

        result[product_key] = row[
            "code_1c"
        ]

    for product_key in sorted(
        product_keys
    ):
        if product_key not in result:
            add_issue(
                issues,
                ERROR,
                "BASE_PRICE_NOT_FOUND",
                product_key,
                (
                    "Для base product_key "
                    "отсутствуют строки "
                    "BaseProductPrice"
                ),
            )

            continue

        if result[product_key] is None:
            add_issue(
                issues,
                ERROR,
                "CODE_1C_EMPTY",
                product_key,
                (
                    "В актуальной записи "
                    "BaseProductPrice "
                    "не заполнен code_1c"
                ),
            )

    return result, issues


# ============================================================
# 7. NOMENCLATURE
# ============================================================


def check_nomenclature_codes(
    product_code_map,
):
    issues = []

    codes = {
        code
        for code in product_code_map.values()
        if code is not None
    }

    if not codes:
        return issues

    rows = list(
        Nomenclature.objects.filter(
            nom_code__in=codes,
        ).values(
            "id",
            "nom_code",
            "nom",
        )
    )

    counts = Counter(
        row["nom_code"]
        for row in rows
    )

    existing_codes = set(
        counts
    )

    for (
        product_key,
        code,
    ) in product_code_map.items():

        if code is None:
            continue

        if code not in existing_codes:
            add_issue(
                issues,
                ERROR,
                "NOMENCLATURE_NOT_FOUND",
                product_key,
                (
                    f"code_1c={code} отсутствует "
                    "в nomenclature.nom_code"
                ),
                product_key=product_key,
                code=code,
            )

        elif counts[code] > 1:
            add_issue(
                issues,
                ERROR,
                "NOMENCLATURE_DUPLICATE",
                product_key,
                (
                    f"В nomenclature найдено "
                    f"{counts[code]} строк "
                    f"с nom_code={code}"
                ),
                product_key=product_key,
                code=code,
            )

    return issues


# ============================================================
# 8. PRODUCT DEPARTURE AGAINST NOMENCLATURE PRICE
# ============================================================


def check_discount_production_regions(
    discount_rows,
    product_code_map,
):
    issues = []

    latest_price_date = (
        NomenclaturePrice.objects.aggregate(
            max_date=Max("date")
        )["max_date"]
    )

    if latest_price_date is None:
        add_issue(
            issues,
            ERROR,
            "NOMENCLATURE_PRICE_EMPTY",
            "",
            "nomenclature_price пустая",
        )

        return issues

    expected_rows = []

    codes = set()

    for row in discount_rows:
        product_key = row[
            "product_key"
        ]

        departure = normalize_text(
            row["departure"]
        )

        code = product_code_map.get(
            product_key
        )

        if (
            code is None
            or not departure
        ):
            continue

        expected_rows.append(
            (
                product_key,
                code,
                departure,
            )
        )

        codes.add(code)

    price_pairs = {
        (
            code,
            (
                normalize_text(
                    shipp_region
                ).casefold()
                if normalize_text(
                    shipp_region
                )
                else None
            ),
        )
        for (
            code,
            shipp_region,
        ) in (
            NomenclaturePrice.objects
            .filter(
                date=latest_price_date,
                code__in=codes,
            )
            .values_list(
                "code",
                "shipp_region",
            )
        )
    }

    for (
        product_key,
        code,
        departure,
    ) in expected_rows:

        key = (
            code,
            departure.casefold(),
        )

        if key not in price_pairs:
            add_issue(
                issues,
                ERROR,
                "PRODUCT_DEPARTURE_NOT_IN_PRICE",
                (
                    f"{product_key}:"
                    f"{departure}"
                ),
                (
                    f"Для code={code}, "
                    f"departure={departure} "
                    "не найдено цены "
                    f"nomenclature_price "
                    f"за {latest_price_date}"
                ),
                product_key=product_key,
                code=code,
                departure=departure,
                price_date=latest_price_date,
            )

    return issues


# ============================================================
# 9. PRODUCT COST
# ============================================================


def check_product_cost(
    selected_codes,
    transport_departures,
):
    issues = []

    rows = list(
        ProductCost.objects.values(
            "id",
            "date",
            "code",
            "name",
            "departure",
            "cost",
        )
    )

    if not rows:
        add_issue(
            issues,
            ERROR,
            "TABLE_EMPTY",
            "",
            "product_cost пустая",
        )

        return rows, issues

    all_codes = {
        row["code"]
        for row in rows
        if row["code"] is not None
    }

    nomenclature_codes = set(
        Nomenclature.objects.filter(
            nom_code__in=all_codes,
        ).values_list(
            "nom_code",
            flat=True,
        )
    )

    normalized_departures = {
        departure.casefold()
        for departure in transport_departures
        if departure
    }

    for row in rows:
        row_id = row["id"]

        code = row["code"]

        departure = normalize_text(
            row["departure"]
        )

        cost = row["cost"]

        if row["date"] is None:
            add_issue(
                issues,
                ERROR,
                "DATE_EMPTY",
                row_id,
                "Не заполнена дата",
            )

        if code is None:
            add_issue(
                issues,
                ERROR,
                "CODE_EMPTY",
                row_id,
                "Не заполнен code",
            )

        elif code not in nomenclature_codes:
            add_issue(
                issues,
                ERROR,
                "CODE_NOT_IN_NOMENCLATURE",
                code,
                (
                    f"code={code} отсутствует "
                    "в nomenclature.nom_code"
                ),
            )

        elif code not in selected_codes:
            add_issue(
                issues,
                ERROR,
                "CODE_NOT_IN_IPRICE",
                code,
                (
                    "code отсутствует среди "
                    "выбранных active base "
                    "товаров iPrice"
                ),
            )

        if not departure:
            add_issue(
                issues,
                ERROR,
                "DEPARTURE_EMPTY",
                row_id,
                "Не заполнен departure",
            )

        elif (
            departure.casefold()
            not in normalized_departures
        ):
            add_issue(
                issues,
                ERROR,
                "DEPARTURE_NOT_IN_TRANSPORT",
                (
                    f"{code}:"
                    f"{departure}"
                ),
                (
                    f"departure={departure} "
                    "не найден среди "
                    "transport_cost.departure"
                ),
            )

        if cost is None:
            add_issue(
                issues,
                ERROR,
                "COST_EMPTY",
                (
                    f"{code}:"
                    f"{departure}"
                ),
                "Не заполнена себестоимость",
            )

        elif cost <= 0:
            add_issue(
                issues,
                ERROR,
                "COST_INVALID",
                (
                    f"{code}:"
                    f"{departure}"
                ),
                (
                    "Себестоимость должна "
                    f"быть > 0, получено {cost}"
                ),
            )

    return rows, issues


# ============================================================
# 10. PRODUCT COST COVERAGE
# ============================================================


def check_product_cost_coverage(
    discount_rows,
    product_code_map,
    product_cost_rows,
):
    issues = []

    product_cost_dates = [
        row["date"]
        for row in product_cost_rows
        if row["date"] is not None
    ]

    if not product_cost_dates:
        return issues

    latest_cost_month = max(
        product_cost_dates
    )

    actual_pairs = {
        (
            row["code"],
            normalize_text(
                row["departure"]
            ).casefold(),
        )
        for row in product_cost_rows
        if (
            row["date"]
            == latest_cost_month
            and row["code"] is not None
            and normalize_text(
                row["departure"]
            )
        )
    }

    for row in discount_rows:
        product_key = row[
            "product_key"
        ]

        departure = normalize_text(
            row["departure"]
        )

        code = product_code_map.get(
            product_key
        )

        if (
            code is None
            or not departure
        ):
            continue

        expected_pair = (
            code,
            departure.casefold(),
        )

        if expected_pair not in actual_pairs:
            add_issue(
                issues,
                ERROR,
                "PRODUCT_COST_MISSING",
                (
                    f"{product_key}:"
                    f"{departure}"
                ),
                (
                    f"Нет себестоимости "
                    f"за {latest_cost_month} "
                    f"для code={code}, "
                    f"departure={departure}"
                ),
                product_key=product_key,
                code=code,
                departure=departure,
                date=latest_cost_month,
            )

    return issues


# ============================================================
# 11. QUANTITY EUROTRUCK
# ============================================================


def check_quantity_eurotruck(
    product_code_map,
):
    """
    Проверяем количество товара в еврофуре
    для каждого выбранного нашего product_key.

    Связь:

        product_key
            ↓
        product_code_map
            ↓
        code_1c
            ↓
        Nomenclature.nom_code
            ↓
        Nomenclature.quantity_eurotruck

    Условия:

    1. Для product_key должен быть определен code_1c.

    2. code_1c должен существовать в Nomenclature.nom_code.

    3. По одному nom_code должна существовать одна
       однозначная строка Nomenclature.

    4. quantity_eurotruck должен быть заполнен.

    5. quantity_eurotruck должен корректно приводиться
       к числу.

    6. quantity_eurotruck должен быть > 0.

    Возвращает:

        {
            product_key: quantity_eurotruck
        }

    и список issues.
    """

    issues = []

    if not product_code_map:
        return {}, issues

    # --------------------------------------------------------
    # Собираем все code_1c, которые удалось определить
    # --------------------------------------------------------

    codes = {
        code
        for code in product_code_map.values()
        if code is not None
    }

    if not codes:
        return {}, issues

    # --------------------------------------------------------
    # Получаем соответствующие строки Nomenclature
    # --------------------------------------------------------

    nomenclature_rows = list(
        Nomenclature.objects.filter(
            nom_code__in=codes,
        ).values(
            "id",
            "nom_code",
            "quantity_eurotruck",
        )
    )

    # --------------------------------------------------------
    # Группируем по nom_code.
    #
    # Используем список, а не простой dict,
    # чтобы обнаруживать дубли nom_code.
    # --------------------------------------------------------

    nomenclature_by_code = defaultdict(
        list
    )

    for row in nomenclature_rows:
        nomenclature_by_code[
            row["nom_code"]
        ].append(row)

    result = {}

    # --------------------------------------------------------
    # Проверяем каждый выбранный product_key
    # --------------------------------------------------------

    for product_key in sorted(
        product_code_map
    ):
        code_1c = product_code_map.get(
            product_key
        )

        # ----------------------------------------------------
        # Нет code_1c
        #
        # Обычно эта ошибка уже должна быть найдена
        # get_current_base_codes(), но здесь оставляем
        # защиту, чтобы функция была самодостаточной.
        # ----------------------------------------------------

        if code_1c is None:
            add_issue(
                issues,
                ERROR,
                "EUROTRUCK_CODE_1C_MISSING",
                product_key,
                (
                    "Невозможно определить количество "
                    "в еврофуре: для product_key "
                    "не найден code_1c"
                ),
                product_key=product_key,
                code_1c=None,
            )

            continue

        nom_rows = (
            nomenclature_by_code.get(
                code_1c,
                [],
            )
        )

        # ----------------------------------------------------
        # code_1c отсутствует в Nomenclature
        # ----------------------------------------------------

        if not nom_rows:
            add_issue(
                issues,
                ERROR,
                "EUROTRUCK_NOMENCLATURE_NOT_FOUND",
                product_key,
                (
                    f"Невозможно определить количество "
                    f"в еврофуре: code_1c={code_1c} "
                    "не найден в nomenclature.nom_code"
                ),
                product_key=product_key,
                code_1c=code_1c,
            )

            continue

        # ----------------------------------------------------
        # Несколько строк с одним nom_code
        #
        # Не выбираем одну произвольно.
        # Это неоднозначная связь.
        # ----------------------------------------------------

        if len(nom_rows) > 1:
            add_issue(
                issues,
                ERROR,
                "EUROTRUCK_NOMENCLATURE_DUPLICATE",
                product_key,
                (
                    f"Невозможно однозначно определить "
                    f"количество в еврофуре: "
                    f"для nom_code={code_1c} "
                    f"в nomenclature найдено "
                    f"{len(nom_rows)} строк"
                ),
                product_key=product_key,
                code_1c=code_1c,
                rows_count=len(
                    nom_rows
                ),
            )

            continue

        nom_row = nom_rows[0]

        raw_quantity = nom_row[
            "quantity_eurotruck"
        ]

        # ----------------------------------------------------
        # Поле пустое / NULL
        # ----------------------------------------------------

        if raw_quantity is None:
            add_issue(
                issues,
                ERROR,
                "EUROTRUCK_QUANTITY_MISSING",
                product_key,
                (
                    "Не заполнено "
                    "nomenclature.quantity_eurotruck "
                    f"для product_key={product_key}, "
                    f"code_1c={code_1c}"
                ),
                product_key=product_key,
                code_1c=code_1c,
            )

            continue

        # ----------------------------------------------------
        # Приводим к Decimal.
        #
        # clean_decimal уже умеет обработать:
        #
        # 500
        # "500"
        # "500,0"
        # "500.0"
        # ----------------------------------------------------

        quantity = clean_decimal(
            raw_quantity
        )

        if quantity is None:
            add_issue(
                issues,
                ERROR,
                "EUROTRUCK_QUANTITY_INVALID",
                product_key,
                (
                    "Поле "
                    "nomenclature.quantity_eurotruck "
                    "содержит некорректное значение: "
                    f"{raw_quantity}"
                ),
                product_key=product_key,
                code_1c=code_1c,
                value=raw_quantity,
            )

            continue

        # ----------------------------------------------------
        # Количество должно быть строго > 0
        # ----------------------------------------------------

        if quantity <= 0:
            add_issue(
                issues,
                ERROR,
                "EUROTRUCK_QUANTITY_NOT_POSITIVE",
                product_key,
                (
                    "Количество в еврофуре должно быть > 0, "
                    f"получено {quantity} "
                    f"для code_1c={code_1c}"
                ),
                product_key=product_key,
                code_1c=code_1c,
                value=str(
                    quantity
                ),
            )

            continue

        # ----------------------------------------------------
        # Все проверки пройдены
        # ----------------------------------------------------

        result[
            product_key
        ] = quantity

    return result, issues


# ============================================================
# 12. IPRICE CALCULATION CONFIG
# ============================================================


def check_iprice_calculation_config():
    issues = []

    rows = list(
        IPriceCalculationConfig.objects.values(
            "id",
            "product_key",
            "departure",
            "arrival",
            "base_analog",
            "base_exclusive",
            "minimum_margin",
            "is_active",
            "date_add",
        )
    )

    if not rows:
        add_issue(
            issues,
            ERROR,
            "TABLE_EMPTY",
            "",
            "iprice_calculation_config пустая",
        )

    active_rows = [row for row in rows if row["is_active"]]
    classifications = {
        row.product_key: row
        for row in ParserProductClassification.objects.filter(
            status=ParserProductClassification.STATUS_ACTIVE,
        )
    }
    product_keys = (
        {row["product_key"] for row in active_rows}
        | set(classifications)
    )
    urls = {
        row.id: row
        for row in ParserProductUrl.objects.filter(id__in=product_keys)
    }
    code_by_product = {}
    for product_key, code_1c in (
        BaseProductPrice.objects.filter(product_key__in=product_keys)
        .exclude(code_1c__isnull=True)
        .order_by("product_key", "-date_add", "-id")
        .values_list("product_key", "code_1c")
    ):
        code_by_product.setdefault(product_key, code_1c)

    arrivals = {
        region.casefold(): region
        for value in ParserPrefix.objects.values_list("shipp_region", flat=True)
        for region in split_regions(value)
        if region and region != "-"
    }
    cost_pairs = {
        (code, departure.casefold())
        for code, departure in ProductCost.objects.values_list("code", "departure")
        if normalize_text(departure)
    }
    discount_pairs = {
        (
            product_key,
            departure.casefold(),
            arrival.casefold(),
        ): departure
        for product_key, departure, arrival in DepartureDiscount.objects.filter(
            is_active=True,
            arrival__isnull=False,
        ).values_list("product_key", "departure", "arrival")
        if normalize_text(departure) and normalize_text(arrival)
    }
    route_pairs = {
        (departure.casefold(), arrival.casefold())
        for departure, arrival in TransportCost.objects.filter(
            is_active=True,
        ).values_list("departure", "arrival")
        if normalize_text(departure) and normalize_text(arrival)
    }
    active_by_key = defaultdict(list)

    for row in rows:
        row_id = row["id"]
        product_key = row["product_key"]
        departure = normalize_text(row["departure"])
        arrival = normalize_text(row["arrival"])
        key_data = {
            "row_id": row_id,
            "product_key": product_key,
            "departure": departure,
            "arrival": arrival,
        }

        if not row["is_active"]:
            continue

        if not departure or departure == "-":
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_DEPARTURE_INVALID",
                row_id,
                "departure должен быть заполнен и не равен '-'",
                **key_data,
            )
        if not arrival or arrival == "-":
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_ARRIVAL_INVALID", row_id,
                "arrival должен быть заполнен и не равен '-'", **key_data,
            )

        classification = classifications.get(product_key)
        item_type = classification.item_type if classification else None
        key_data["item_type"] = item_type
        if classification is None:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_CLASSIFICATION_MISSING", row_id,
                "Нет активной классификации для product_key", **key_data,
            )
        elif item_type not in {
            ParserProductClassification.ITEM_TYPE_PRODUCT,
            ParserProductClassification.ITEM_TYPE_COMPONENT,
        }:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_ITEM_TYPE_INVALID", row_id,
                "item_type в parser_product_classification некорректен", **key_data,
            )

        url = urls.get(product_key)
        url_source = normalize_text(url.source) if url is not None else None
        if (
            url is None
            or url.status != ParserProductUrl.STATUS_ACTIVE
            or not url_source
            or url_source.casefold() != "base"
        ):
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_BASE_PRODUCT_INVALID", row_id,
                "product_key должен соответствовать активному базовому товару",
                **key_data,
            )

        code_1c = code_by_product.get(product_key)
        key_data["code_1c"] = code_1c
        if code_1c is None:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_CODE_1C_MISSING", row_id,
                "Для product_key не найден актуальный code_1c", **key_data,
            )
        elif departure and (code_1c, departure.casefold()) not in cost_pairs:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_PRODUCT_COST_MISSING", row_id,
                "Не найдена себестоимость для code_1c + departure", **key_data,
            )

        if (
            departure
            and arrival
            and (
                product_key,
                departure.casefold(),
                arrival.casefold(),
            ) not in discount_pairs
        ):
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_DISCOUNT_MISSING", row_id,
                "Не найдена активная скидка для полного маршрута", **key_data,
            )
        if arrival and arrival.casefold() not in arrivals:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_ARRIVAL_UNKNOWN", row_id,
                "arrival отсутствует в parser_prefix.shipp_region", **key_data,
            )
        if departure and arrival and departure.casefold() != arrival.casefold() and (
            departure.casefold(), arrival.casefold()
        ) not in route_pairs:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_ROUTE_MISSING", row_id,
                "Не найден активный маршрут departure + arrival", **key_data,
            )

        if departure and arrival:
            active_by_key[(product_key, departure.casefold(), arrival.casefold())].append(row)

        base_analog = row[
            "base_analog"
        ]

        base_exclusive = row[
            "base_exclusive"
        ]

        minimum_margin = row[
            "minimum_margin"
        ]

        if base_analog is None:
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_BASE_ANALOG_EMPTY",
                row_id,
                "Не заполнено поле base_analog",
                **key_data,
                field="base_analog",
            )

        elif base_analog < Decimal("0"):
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_BASE_ANALOG_INVALID",
                row_id,
                (
                    "base_analog должен быть >= 0, "
                    f"получено {base_analog}"
                ),
                **key_data,
                field="base_analog",
                value=str(base_analog),
            )

        if base_exclusive is None:
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_BASE_EXCLUSIVE_EMPTY",
                row_id,
                "Не заполнено поле base_exclusive",
                **key_data,
                field="base_exclusive",
            )

        elif not (
            Decimal("0")
            < base_exclusive
            < Decimal("1")
        ):
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_BASE_EXCLUSIVE_INVALID",
                row_id,
                (
                    "base_exclusive должен быть "
                    "больше 0 и меньше 1, "
                    f"получено {base_exclusive}"
                ),
                **key_data,
                field="base_exclusive",
                value=str(base_exclusive),
            )

        if minimum_margin is None:
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_MINIMUM_MARGIN_EMPTY",
                row_id,
                "Не заполнено поле minimum_margin",
                **key_data,
                field="minimum_margin",
            )

        elif not (
            Decimal("0")
            <= minimum_margin
            < Decimal("1")
        ):
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_MINIMUM_MARGIN_INVALID",
                row_id,
                (
                    "minimum_margin должен быть "
                    "не меньше 0 и меньше 1, "
                    f"получено {minimum_margin}"
                ),
                **key_data,
                field="minimum_margin",
                value=str(minimum_margin),
            )

    for key, duplicate_rows in active_by_key.items():
        if len(duplicate_rows) > 1:
            product_key, departure, arrival = key
            add_issue(
                issues,
                ERROR,
                "IPRICE_CONFIG_ACTIVE_DUPLICATE",
                f"{product_key}:{departure}->{arrival}",
                "Найдено несколько активных конфигураций для одной комбинации",
                product_key=product_key,
                departure=departure,
                arrival=arrival,
                active_ids=[row["id"] for row in duplicate_rows],
            )

    expected_product_keys = set(
        ParserProductClassification.objects.filter(
            status=ParserProductClassification.STATUS_ACTIVE,
            product_key__in=ParserProductUrl.objects.filter(
                status=ParserProductUrl.STATUS_ACTIVE,
                source="base",
            ).values_list("id", flat=True),
        ).values_list("product_key", flat=True)
    )
    for (
        product_key,
        departure_key,
        arrival_key,
    ), departure in discount_pairs.items():
        if product_key not in expected_product_keys:
            continue
        arrival = arrivals.get(arrival_key, arrival_key)
        if (product_key, departure_key, arrival_key) not in active_by_key:
            add_issue(
                issues, ERROR, "IPRICE_CONFIG_ACTIVE_MISSING",
                f"{product_key}:{departure}->{arrival}",
                "Отсутствует активная конфигурация для расчётной комбинации",
                product_key=product_key,
                departure=departure,
                arrival=arrival,
                item_type=(
                    classifications[product_key].item_type
                    if product_key in classifications else None
                ),
                code_1c=code_by_product.get(product_key),
            )

    return rows, issues


# ============================================================
# 13. PREFIX MAP
# ============================================================


def build_prefix_region_map():
    """
    Возвращает:

    {
        (source_lower, prefix_lower): [
            "Москва",
            "Ставрово",
        ]
    }
    """

    result = {}

    rows = ParserPrefix.objects.values(
        "source",
        "prefix",
        "shipp_region",
    )

    for row in rows:
        source = normalize_text(
            row["source"]
        )

        prefix = normalize_text(
            row["prefix"]
        )

        if not source or not prefix:
            continue

        result[
            (
                source.casefold(),
                prefix.casefold(),
            )
        ] = split_regions(
            row["shipp_region"]
        )

    return result


# ============================================================
# 14. EXACT TRANSPORT ROUTE COVERAGE
# ============================================================


def check_transport_route_coverage(
    match_rows,
    discount_rows,
):
    """
    Проверяем наличие транспортных маршрутов для реальных
    комбинаций:

        наш товар
            ↓
        DepartureDiscount.departure
            ↓
        регион производства

        competitor
            ↓
        ParserProductUrl.source + prefix
            ↓
        регион(ы) продаж arrival

    Логика определения arrival:

    1. Если для source конкурента вообще НЕТ записей
       в ParserPrefix:
           источник считается не имеющим настроенной
           региональной разбивки;
           транспортные маршруты для его competitor
           в этой проверке НЕ проверяются.

    2. Если для source записи ParserPrefix существуют
       и prefix != "-":
           source + prefix
               ↓
           ParserPrefix
               ↓
           shipp_region
               ↓
           arrival

       Если конкретной пары source + prefix нет:
           ERROR.

    3. Если для source записи ParserPrefix существуют,
       но у конкретного competitor prefix == "-":
           у конкретного товара конкурента нет собственной
           региональной разбивки;
           он относится ко всем нашим регионам продаж.

            Наши регионы продаж берем из:
            ParserPrefix.shipp_region

            Поле может содержать несколько регионов,
            разделенных точкой с запятой.

           При этом пустые значения и "-" регионами
           не считаются.

    Проверка транспорта:

    - departure == arrival:
          транспорт = 0;
          строка TransportCost НЕ требуется;

    - departure != arrival:
          должна существовать конкретная строка
          TransportCost(departure, arrival).
    """

    issues = []

    if not match_rows:
        return issues

    # ========================================================
    # 1. РЕГИОНЫ ПРОИЗВОДСТВА НАШИХ ТОВАРОВ
    #
    # Источник истины:
    # DepartureDiscount.product_key + departure
    # ========================================================

    departures_by_product = defaultdict(set)

    for row in discount_rows:
        product_key = row[
            "product_key"
        ]

        departure = normalize_text(
            row["departure"]
        )

        if departure:
            departures_by_product[
                product_key
            ].add(
                departure
            )

    # ========================================================
    # 2. ДАННЫЕ КОНКУРЕНТОВ ИЗ ParserProductUrl
    # ========================================================

    competitor_keys = {
        row[
            "product_key_competitor"
        ]
        for row in match_rows
    }

    competitor_urls = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=competitor_keys,
            )
            .values(
                "id",
                "source",
                "prefix",
            )
        )
    }

    # ========================================================
    # 3. НАСТРОЕННЫЕ PREFIX -> REGION
    #
    # Стандартная карта:
    #
    # (source, prefix)
    #       ->
    # [region1, region2, ...]
    # ========================================================

    prefix_map = (
        build_prefix_region_map()
    )

    # ========================================================
    # 4. ИСТОЧНИКИ, ДЛЯ КОТОРЫХ ВООБЩЕ НАСТРОЕНЫ PREFIX
    #
    # ВАЖНО:
    #
    # Если source отсутствует здесь полностью,
    # мы считаем, что региональная разбивка для этого
    # источника не используется.
    #
    # Для таких source эта функция НЕ проверяет маршруты.
    # ========================================================

    sources_with_prefix_config = set()

    prefix_source_values = (
        ParserPrefix.objects
        .exclude(
            source__isnull=True,
        )
        .exclude(
            source="",
        )
        .values_list(
            "source",
            flat=True,
        )
        .distinct()
    )

    for value in prefix_source_values:
        source_value = normalize_text(
            value
        )

        if (
            source_value
            and source_value != "-"
        ):
            sources_with_prefix_config.add(
                source_value.casefold()
            )

    # ========================================================
    # 5. ВСЕ НАШИ РЕАЛЬНЫЕ РЕГИОНЫ ПРОДАЖ
    #
    # Используются только для случая:
    #
    # source настроен в ParserPrefix,
    # но competitor.prefix == "-"
    #
    # NomenclaturePrice.shipp_region = регион продажи.
    #
    # Значение "-" не является регионом и исключается.
    # ========================================================

    all_sales_regions = set()

    prefix_region_values = (
        ParserPrefix.objects
        .exclude(
            shipp_region__isnull=True,
        )
        .exclude(
            shipp_region="",
        )
        .values_list(
            "shipp_region",
            flat=True,
        )
    )

    for value in prefix_region_values:
        for region in split_regions(value):
            normalized_region = normalize_text(region)

            if (
                normalized_region
                and normalized_region != "-"
            ):
                all_sales_regions.add(
                    normalized_region
                )

    # ========================================================
    # 6. СУЩЕСТВУЮЩИЕ ТРАНСПОРТНЫЕ МАРШРУТЫ
    #
    # Храним нормализованными:
    #
    # (
    #     departure.casefold(),
    #     arrival.casefold(),
    # )
    # ========================================================

    transport_pairs = set()

    for (
        departure,
        arrival,
    ) in (
        TransportCost.objects
        .filter(
            is_active=True,
        )
        .values_list(
            "departure",
            "arrival",
        )
    ):
        pair = normalized_pair(
            departure,
            arrival,
        )

        if pair:
            transport_pairs.add(
                pair
            )

    # ========================================================
    # 7. ЗАЩИТА ОТ ПОВТОРНЫХ ПРОВЕРОК
    # ========================================================

    checked = set()

    # ========================================================
    # 8. ОСНОВНОЙ ЦИКЛ ПО MATCH
    # ========================================================

    for match in match_rows:
        base_key = match[
            "product_key_base"
        ]

        competitor_key = match[
            "product_key_competitor"
        ]

        # ----------------------------------------------------
        # Производства нашего товара
        # ----------------------------------------------------

        departures = (
            departures_by_product.get(
                base_key,
                set(),
            )
        )

        if not departures:
            add_issue(
                issues,
                ERROR,
                "BASE_DEPARTURE_MISSING",
                base_key,
                (
                    "Для product_key_base "
                    "нет строк DepartureDiscount, "
                    "поэтому невозможно определить "
                    "регион производства"
                ),
                product_key_base=base_key,
            )

            continue

        # ----------------------------------------------------
        # Данные competitor
        # ----------------------------------------------------

        competitor_url = (
            competitor_urls.get(
                competitor_key
            )
        )

        if competitor_url is None:
            # Ошибка существования competitor уже
            # определяется в check_matches().
            continue

        source = normalize_text(
            competitor_url["source"]
        )

        prefix = normalize_text(
            competitor_url["prefix"]
        )

        if not source or not prefix:
            # Пустой source/prefix уже проверяется
            # в check_matches().
            continue

        source_key = (
            source.casefold()
        )

        # ====================================================
        # ОСОБОЕ ПРАВИЛО №1
        #
        # Для данного source вообще нет ни одной строки
        # в ParserPrefix.
        #
        # Значит региональная разбивка этого источника
        # в системе не настроена.
        #
        # НЕ:
        #   - создаем ошибку PREFIX_REGION_MAPPING_MISSING;
        #   - строим departure × arrival;
        #   - проверяем TransportCost.
        #
        # Просто исключаем этот competitor из проверки
        # транспортных маршрутов.
        # ====================================================

        if (
            source_key
            not in sources_with_prefix_config
        ):
            continue

        # ====================================================
        # 9. ОПРЕДЕЛЯЕМ ARRIVAL
        # ====================================================

        if prefix == "-":
            # =================================================
            # ОСОБОЕ ПРАВИЛО №2
            #
            # Source имеет региональную настройку вообще,
            # но у конкретного competitor prefix = "-".
            #
            # Значит сам competitor не разбит по регионам
            # и относится ко всем нашим регионам продаж.
            # =================================================

            arrivals = sorted(
                all_sales_regions,
                key=lambda value: (
                    value.casefold()
                ),
            )

            if not arrivals:
                add_issue(
                    issues,
                    ERROR,
                    "SALES_REGIONS_NOT_FOUND",
                    (
                        f"{source}:"
                        f"{prefix}"
                    ),
                    (
                        "Для competitor с prefix='-' "
                        "не удалось определить "
                        "наши регионы продаж: "
                        "в nomenclature_price отсутствуют "
                        "корректные shipp_region"
                    ),
                    source=source,
                    prefix=prefix,
                    competitor_product_key=(
                        competitor_key
                    ),
                )

                continue

        else:
            # =================================================
            # ОБЫЧНЫЙ СЛУЧАЙ
            #
            # source + prefix
            #       ↓
            # ParserPrefix
            #       ↓
            # shipp_region
            #       ↓
            # arrival
            # =================================================

            arrivals = prefix_map.get(
                (
                    source_key,
                    prefix.casefold(),
                )
            )

            if not arrivals:
                add_issue(
                    issues,
                    ERROR,
                    "PREFIX_REGION_MAPPING_MISSING",
                    (
                        f"{source}:"
                        f"{prefix}"
                    ),
                    (
                        "Для source настроена "
                        "региональная разбивка, "
                        "но для конкретного "
                        "source/prefix отсутствует "
                        "сопоставление региона продаж "
                        "в parser_prefix"
                    ),
                    source=source,
                    prefix=prefix,
                    competitor_product_key=(
                        competitor_key
                    ),
                )

                continue

        # ====================================================
        # 10. ПРОВЕРЯЕМ DEPARTURE × ARRIVAL
        # ====================================================

        for departure in departures:
            for arrival in arrivals:
                departure_norm = (
                    normalize_text(
                        departure
                    )
                )

                arrival_norm = (
                    normalize_text(
                        arrival
                    )
                )

                # --------------------------------------------
                # Некорректные значения пропускаем.
                # Они должны быть пойманы другими validation.
                # --------------------------------------------

                if (
                    not departure_norm
                    or not arrival_norm
                ):
                    continue

                # "-" не является регионом.
                if (
                    departure_norm == "-"
                    or arrival_norm == "-"
                ):
                    continue

                # --------------------------------------------
                # Уникальная проверяемая комбинация
                # --------------------------------------------

                unique_key = (
                    base_key,
                    competitor_key,
                    departure_norm.casefold(),
                    arrival_norm.casefold(),
                )

                if unique_key in checked:
                    continue

                checked.add(
                    unique_key
                )

                # ============================================
                # 11. ОДИНАКОВЫЙ РЕГИОН
                #
                # Регион производства == регион продажи.
                #
                # Например:
                #
                # Ставрово -> Ставрово
                #
                # TransportCost искать НЕ надо.
                #
                # Транспорт при расчете = 0.
                # ============================================

                if not route_requires_transport(
                    departure_norm,
                    arrival_norm,
                ):
                    continue

                # ============================================
                # 12. РЕГИОНЫ РАЗНЫЕ
                #
                # Требуется конкретный TransportCost.
                # ============================================

                pair = normalized_pair(
                    departure_norm,
                    arrival_norm,
                )

                if pair not in transport_pairs:
                    add_issue(
                        issues,
                        ERROR,
                        "TRANSPORT_ROUTE_MISSING",
                        (
                            f"{base_key}:"
                            f"{departure_norm}->"
                            f"{arrival_norm}"
                        ),
                        (
                            "Не найден маршрут "
                            f"{departure_norm} -> "
                            f"{arrival_norm} "
                            "в transport_cost"
                        ),
                        product_key_base=(
                            base_key
                        ),
                        competitor_product_key=(
                            competitor_key
                        ),
                        source=source,
                        prefix=prefix,
                        departure=(
                            departure_norm
                        ),
                        arrival=(
                            arrival_norm
                        ),
                    )

    return issues

# ============================================================
# 15. MAIN CHECK
# ============================================================


def run_iprice_preparation_check():
    results = {}

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    (
        classification_rows,
        classification_issues,
    ) = check_classification()

    active_classification_keys = {
        row["product_key"]
        for row in classification_rows
    }

    results[
        "parser_product_classification"
    ] = {
        "checked": len(
            classification_rows
        ),
        "issues": (
            classification_issues
        ),
    }

    # ========================================================
    # MATCH
    # ========================================================

    (
        match_rows,
        match_issues,
    ) = check_matches(
        active_classification_keys
    )

    results[
        "parser_product_match"
    ] = {
        "checked": len(
            match_rows
        ),
        "issues": match_issues,
    }

    # ========================================================
    # TRANSPORT
    # ========================================================

    (
        transport_rows,
        transport_issues,
    ) = check_transport_cost()

    transport_departures = {
        normalize_text(
            row["departure"]
        )
        for row in transport_rows
        if normalize_text(
            row["departure"]
        )
    }

    transport_arrivals = {
        normalize_text(
            row["arrival"]
        )
        for row in transport_rows
        if normalize_text(
            row["arrival"]
        )
    }

    # Регион может оказаться только departure,
    # например когда shipment region совпадает
    # с arrival и транспорт = 0.
    #
    # Поэтому prefix нельзя валидировать только
    # против transport_cost.arrival.
    known_transport_regions = (
        transport_departures
        | transport_arrivals
    )

    results[
        "transport_cost"
    ] = {
        "checked": len(
            transport_rows
        ),
        "issues": transport_issues,
    }

    # ========================================================
    # PREFIX
    # ========================================================

    (
        prefix_rows,
        prefix_issues,
    ) = check_prefixes(
        known_transport_regions
    )

    results[
        "parser_prefix"
    ] = {
        "checked": len(
            prefix_rows
        ),
        "issues": prefix_issues,
    }

    # ========================================================
    # DEPARTURE DISCOUNT
    # ========================================================

    (
        discount_rows,
        discount_issues,
    ) = check_departure_discount(
        active_classification_keys,
        transport_departures,
    )

    # ========================================================
    # IPRICE CALCULATION CONFIG
    # ========================================================

    (
        calculation_config_rows,
        calculation_config_issues,
    ) = check_iprice_calculation_config()

    results[
        "iprice_calculation_config"
    ] = {
        "checked": (
            len(calculation_config_rows)
            + len(discount_rows)
        ),
        "issues": (
            discount_issues
            + calculation_config_issues
        ),
    }

    # ========================================================
    # ACTIVE BASE SET
    # ========================================================

    active_base_keys = set(
        ParserProductUrl.objects.filter(
            id__in=(
                active_classification_keys
            ),
            source="base",
            status=(
                ParserProductUrl.STATUS_ACTIVE
            ),
        ).values_list(
            "id",
            flat=True,
        )
    )

    # ========================================================
    # BASE -> CODE 1C
    # ========================================================

    (
        product_code_map,
        base_code_issues,
    ) = get_current_base_codes(
        active_base_keys
    )

    # ========================================================
    # NOMENCLATURE
    # ========================================================

    nomenclature_issues = (
        check_nomenclature_codes(
            product_code_map
        )
    )

    # ========================================================
    # NOMENCLATURE PRICE / PRODUCTION
    # ========================================================

    production_region_issues = (
        check_discount_production_regions(
            discount_rows,
            product_code_map,
        )
    )

    # ========================================================
    # QUANTITY EUROTRUCK
    # ========================================================

    (
        quantity_eurotruck_map,
        quantity_eurotruck_issues,
    ) = check_quantity_eurotruck(
        product_code_map
    )

    # quantity_eurotruck_map пригодится позже
    # непосредственно в running snapshot.
    #
    # Сейчас нам важна сама валидация.

    # ========================================================
    # PRODUCT COST
    # ========================================================

    selected_codes = {
        code
        for code in product_code_map.values()
        if code is not None
    }

    (
        product_cost_rows,
        product_cost_issues,
    ) = check_product_cost(
        selected_codes,
        transport_departures,
    )

    results[
        "product_cost"
    ] = {
        "checked": len(
            product_cost_rows
        ),
        "issues": product_cost_issues,
    }

    # ========================================================
    # PRODUCT COST COVERAGE
    # ========================================================

    product_cost_coverage_issues = (
        check_product_cost_coverage(
            discount_rows,
            product_code_map,
            product_cost_rows,
        )
    )

    # ========================================================
    # EXACT TRANSPORT ROUTES
    # ========================================================

    transport_route_issues = (
        check_transport_route_coverage(
            match_rows,
            discount_rows,
        )
    )

    # ========================================================
    # CROSS CHECKS
    # ========================================================

    cross_issues = (
        base_code_issues
        + nomenclature_issues
        + production_region_issues
        + quantity_eurotruck_issues
        + product_cost_coverage_issues
        + transport_route_issues
    )

    results[
        "cross_checks"
    ] = {
        "checked": len(
            active_base_keys
        ),
        "issues": cross_issues,
    }

    return results


# ============================================================
# EXCEL
# ============================================================


def _append_header(
    worksheet,
    headers,
):
    worksheet.append(headers)

    for cell in worksheet[1]:
        cell.font = Font(
            bold=True
        )


def _autosize_worksheet(
    worksheet,
):
    for column_cells in (
        worksheet.columns
    ):
        max_length = 0

        for cell in column_cells:
            value = cell.value

            if value is None:
                continue

            max_length = max(
                max_length,
                len(str(value)),
            )

        column_letter = (
            get_column_letter(
                column_cells[0].column
            )
        )

        worksheet.column_dimensions[
            column_letter
        ].width = min(
            max(
                max_length + 2,
                12,
            ),
            80,
        )


def export_iprice_preparation_check():
    results = (
        run_iprice_preparation_check()
    )

    workbook = Workbook()

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = workbook.active
    summary.title = "Summary"

    _append_header(
        summary,
        [
            "Таблица",
            "Проверено",
            "Ошибок",
            "Предупреждений",
            "Статус",
        ],
    )

    total_errors = 0
    total_warnings = 0

    for (
        table_name,
        result,
    ) in results.items():

        issues = result[
            "issues"
        ]

        errors = sum(
            1
            for issue in issues
            if issue["level"] == ERROR
        )

        warnings = sum(
            1
            for issue in issues
            if issue["level"] == WARNING
        )

        total_errors += errors
        total_warnings += warnings

        if errors:
            table_status = "ERROR"

        elif warnings:
            table_status = "WARNING"

        else:
            table_status = "OK"

        summary.append([
            table_name,
            result["checked"],
            errors,
            warnings,
            table_status,
        ])

    summary.freeze_panes = "A2"
    summary.auto_filter.ref = (
        summary.dimensions
    )

    _autosize_worksheet(
        summary
    )

    # ========================================================
    # ISSUE SHEETS
    # ========================================================

    issue_headers = [
        "Уровень",
        "Код ошибки",
        "Ключ",
        "Описание",
        "Дополнительные данные",
    ]

    for (
        table_name,
        result,
    ) in results.items():

        worksheet = (
            workbook.create_sheet(
                title=table_name[:31]
            )
        )

        _append_header(
            worksheet,
            issue_headers,
        )

        for issue in result[
            "issues"
        ]:
            extra = {
                key: value
                for (
                    key,
                    value,
                ) in issue.items()
                if key not in {
                    "level",
                    "error_code",
                    "business_key",
                    "message",
                }
            }

            worksheet.append([
                issue[
                    "level"
                ],
                issue[
                    "error_code"
                ],
                issue[
                    "business_key"
                ],
                issue[
                    "message"
                ],
                (
                    str(extra)
                    if extra
                    else ""
                ),
            ])

        worksheet.freeze_panes = (
            "A2"
        )

        worksheet.auto_filter.ref = (
            worksheet.dimensions
        )

        _autosize_worksheet(
            worksheet
        )

    # ========================================================
    # RESULT
    # ========================================================

    output = BytesIO()

    workbook.save(
        output
    )

    output.seek(0)

    if total_errors:
        check_status = "error"

    elif total_warnings:
        check_status = "warning"

    else:
        check_status = "ok"

    return output, {
        "status": check_status,
        "errors": total_errors,
        "warnings": total_warnings,
    }
