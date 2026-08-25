from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from django.db.models import Q

from datasets.models import (
    IPriceSnapshotProduct,
    ParserPrefix,
    ParserProductClassification,
    ParserProductMatch,
    ParserProductUrl,
)

from datasets.services.parsers.regional_product_groups import (
    build_competitor_url_groups,
    get_prefixes_by_source,
)
from datasets.services.iprice_source_selector import (
    get_competitor_price_data,
    positive_price_or_none,
)


# ============================================================
# EXCEPTIONS
# ============================================================


class IPriceMarketAssortmentError(Exception):
    """
    Ошибка формирования справочного
    рыночного ассортимента.
    """


# ============================================================
# NORMALIZATION
# ============================================================


def clean_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def normalized_text(
    value: Any,
) -> str | None:
    """
    Нормализует значение для сравнения:

    - удаляет пробелы по краям;
    - приводит к нижнему регистру;
    - повторные внутренние пробелы
      заменяет одним.
    """

    value = clean_text(value)

    if value is None:
        return None

    return " ".join(
        value.casefold().split()
    )


def split_regions(
    value: Any,
) -> list[str]:
    """
    ParserPrefix.shipp_region может содержать:

        Москва;Ставрово

    Возвращает отдельные регионы без дублей.
    """

    value = clean_text(value)

    if value is None:
        return []

    result = []
    seen = set()

    for part in value.split(";"):
        region = clean_text(part)

        if region is None:
            continue

        region_key = region.casefold()

        if region_key in seen:
            continue

        seen.add(region_key)
        result.append(region)

    return result


# ============================================================
# PREFIX AND REGION DATA
# ============================================================


def build_prefix_region_map() -> dict:
    """
    Возвращает:

        (source, prefix)
            ->
        [регион 1, регион 2]

    Сравнение source и prefix выполняется
    без учёта регистра.
    """

    result = defaultdict(list)
    seen_by_key = defaultdict(set)

    rows = (
        ParserPrefix.objects
        .all()
        .values(
            "source",
            "prefix",
            "shipp_region",
        )
        .order_by(
            "source",
            "prefix",
        )
    )

    for row in rows:
        source = normalized_text(
            row["source"]
        )

        prefix = normalized_text(
            row["prefix"]
        )

        if (
            source is None
            or prefix is None
        ):
            continue

        key = (
            source,
            prefix,
        )

        region = clean_text(row["shipp_region"])
        if region:
            region = ";".join(split_regions(region))

        if region:
            region_key = region.casefold()

            if (
                region_key
                in seen_by_key[key]
            ):
                continue

            seen_by_key[key].add(
                region_key
            )

            result[key].append(
                region
            )

    return dict(result)


def get_url_regions(
    *,
    source: str | None,
    prefix: str | None,
    prefix_region_map: dict,
) -> list[str]:
    source_key = normalized_text(
        source
    )

    prefix_key = normalized_text(
        prefix
    )

    if (
        source_key is None
        or prefix_key is None
    ):
        return []

    return list(
        prefix_region_map.get(
            (
                source_key,
                prefix_key,
            ),
            [],
        )
    )


# ============================================================
# CLASSIFICATION SELECTION
# ============================================================


def validate_snapshot_product_classification(
    snapshot_product: IPriceSnapshotProduct,
):
    """
    Справочный подбор возможен только по четырём
    обязательным классификационным полям.
    """

    required_fields = (
        "category",
        "subcategory",
        "subcategory_type",
        "item_type",
    )

    empty_fields = [
        field_name
        for field_name in required_fields
        if clean_text(
            getattr(
                snapshot_product,
                field_name,
                None,
            )
        )
        is None
    ]

    if empty_fields:
        raise IPriceMarketAssortmentError(
            (
                "Невозможно подобрать рыночный "
                "ассортимент: у товара snapshot "
                "не заполнены поля "
                f"{', '.join(empty_fields)}"
            )
        )


def get_market_classifications(
    *,
    snapshot_product: IPriceSnapshotProduct,
) -> list[ParserProductClassification]:
    """
    Отбирает все активные классификации
    при точном совпадении:

        category
        subcategory
        subcategory_type
        item_type

    material, color и modification
    в фильтрации не участвуют.
    """

    validate_snapshot_product_classification(
        snapshot_product
    )

    queryset = (
        ParserProductClassification.objects
        .filter(
            status=(
                ParserProductClassification
                .STATUS_ACTIVE
            ),
            category__iexact=(
                clean_text(
                    snapshot_product.category
                )
            ),
            subcategory__iexact=(
                clean_text(
                    snapshot_product.subcategory
                )
            ),
            subcategory_type__iexact=(
                clean_text(
                    snapshot_product
                    .subcategory_type
                )
            ),
            item_type__iexact=(
                clean_text(
                    snapshot_product.item_type
                )
            ),
        )
        .order_by(
            "product_key",
        )
    )

    return list(queryset)


# ============================================================
# URL GROUPING
# ============================================================


def build_market_group_key_map(
    *,
    competitor_product_keys: set[int],
) -> dict[int, tuple]:
    """
    Возвращает ключ карточки для каждого competitor product_key.

    Для source, у которого есть региональная конфигурация
    ParserPrefix, используется та же группировка, что и
    при автоматическом создании ParserProductMatch:

        source + normalized_url

    Для source без ParserPrefix, например TT,
    региональное объединение не выполняется:

        source + product_key
    """

    if not competitor_product_keys:
        return {}

    prefixes_by_source = (
        get_prefixes_by_source()
    )

    (
        _,
        url_group_key_by_product,
    ) = build_competitor_url_groups(
        prefixes_by_source=(
            prefixes_by_source
        )
    )

    url_rows = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=(
                    competitor_product_keys
                ),
                status=(
                    ParserProductUrl
                    .STATUS_ACTIVE
                ),
            )
            .exclude(
                source="base",
            )
            .values(
                "id",
                "source",
            )
        )
    }

    result = {}

    for product_key in sorted(
        competitor_product_keys
    ):
        url_row = url_rows.get(
            product_key
        )

        if url_row is None:
            continue

        source = normalized_text(
            url_row["source"]
        )

        if source is None:
            continue

        configured_group_key = (
            url_group_key_by_product.get(
                product_key
            )
        )

        if configured_group_key is not None:
            result[product_key] = (
                "url_group",
                *configured_group_key,
            )

        else:
            # Источник без региональной разбивки
            # или URL, который невозможно сгруппировать.
            result[product_key] = (
                "single",
                source,
                product_key,
            )

    return result


# ============================================================
# MATCH AND SNAPSHOT FLAGS
# ============================================================


def get_match_data(
    *,
    competitor_product_keys: set[int],
    current_base_product_key: int,
) -> dict:
    """
    Для каждого competitor product_key возвращает:

        is_matched_any
        is_matched_current
        matched_base_product_keys
        match_types
    """

    result = {
        product_key: {
            "is_matched_any": False,
            "is_matched_current": False,
            "matched_base_product_keys": set(),
            "match_types": set(),
        }
        for product_key
        in competitor_product_keys
    }

    if not competitor_product_keys:
        return result

    rows = (
        ParserProductMatch.objects
        .filter(
            product_key_competitor__in=(
                competitor_product_keys
            ),
            status=(
                ParserProductMatch
                .STATUS_ACTIVE
            ),
        )
        .values(
            "product_key_base",
            "product_key_competitor",
            "match_type",
        )
    )

    for row in rows:
        competitor_key = row[
            "product_key_competitor"
        ]

        item = result.get(
            competitor_key
        )

        if item is None:
            continue

        base_key = row[
            "product_key_base"
        ]

        item["is_matched_any"] = True

        item[
            "matched_base_product_keys"
        ].add(
            base_key
        )

        match_type = clean_text(
            row["match_type"]
        )

        if match_type:
            item["match_types"].add(
                match_type
            )

        if (
            base_key
            == current_base_product_key
        ):
            item[
                "is_matched_current"
            ] = True

    return result


def get_snapshot_competitor_keys(
    *,
    snapshot_product: IPriceSnapshotProduct,
) -> set[int]:
    """
    Конкуренты, реально сохранённые
    в выбранном snapshot для этого товара.
    """

    return set(
        snapshot_product.competitors
        .all()
        .values_list(
            "competitor_product_key",
            flat=True,
        )
    )


# ============================================================
# CARD BUILDING
# ============================================================


def choose_representative_variant(
    variants: list[dict],
) -> dict:
    """
    Представителем объединённой карточки становится:

    1. наиболее похожий вариант;
    2. использованный в snapshot;
    3. смэченный с текущим товаром;
    4. ручная классификация;
    5. вариант с меньшим product_key.
    """

    def sort_key(
        variant: dict,
    ):
        return (
            -int(
                variant["is_used_in_snapshot"]
            ),
            -int(
                variant["is_matched_current"]
            ),
            variant["product_key"],
        )

    return sorted(
        variants,
        key=sort_key,
    )[0]


def build_market_card(
    *,
    group_key: tuple,
    variants: list[dict],
) -> dict:
    representative = (
        choose_representative_variant(
            variants
        )
    )

    valid_prices = [
        variant["price"]
        for variant in variants
        if positive_price_or_none(variant["price"]) is not None
    ]
    market_median = (
        median(valid_prices)
        if valid_prices
        else None
    )

    regions = []
    seen_regions = set()

    product_keys = []
    matched_base_product_keys = set()
    match_types = set()

    for variant in sorted(
        variants,
        key=lambda item: (
            item["source"] or "",
            item["prefix"] or "",
            item["product_key"],
        ),
    ):
        product_keys.append(
            variant["product_key"]
        )

        matched_base_product_keys.update(
            variant[
                "matched_base_product_keys"
            ]
        )

        match_types.update(
            variant["match_types"]
        )

        for region in variant["regions"]:
            region_key = region.casefold()

            if region_key in seen_regions:
                continue

            seen_regions.add(
                region_key
            )

            regions.append(
                region
            )

    regions.sort(
        key=str.casefold
    )

    return {
        "group_key": "|".join(
            str(value)
            for value in group_key
        ),

        "source": (
            representative["source"]
        ),

        "name": representative.get("name"),

        "product_key": (
            representative["product_key"]
        ),

        "product_keys": sorted(
            product_keys
        ),

        "category": (
            representative["category"]
        ),
        "subcategory": (
            representative["subcategory"]
        ),
        "subcategory_type": (
            representative[
                "subcategory_type"
            ]
        ),
        "item_type": (
            representative["item_type"]
        ),

        # Эти поля не ограничивают выборку,
        # но отражаются информационно.
        "material": (
            representative["material"]
        ),
        "color": (
            representative["color"]
        ),
        "modification": (
            representative["modification"]
        ),
        "article_number_analogs": representative.get("article_number_analogs"),
        "additional_property": (
            representative.get("additional_property")
        ),

        "url": representative["url"],
        "image": representative["image"],
        "price": market_median,


        "is_matched_any": any(
            variant["is_matched_any"]
            for variant in variants
        ),

        "is_matched_current": any(
            variant[
                "is_matched_current"
            ]
            for variant in variants
        ),

        "is_used_in_snapshot": any(
            variant[
                "is_used_in_snapshot"
            ]
            for variant in variants
        ),
        "is_price_used_in_calculation": market_median is not None,

        "matched_base_product_keys": (
            sorted(
                matched_base_product_keys
            )
        ),

        "match_types": sorted(
            match_types
        ),

        "regions": regions,

        "price_variants": [
            price_variant
            for variant in variants
            for price_variant in variant.get("price_variants", [])
        ],

        "regional_variants_count": len(
            variants
        ),

        "variants": [
            {
                key: value
                for key, value
                in variant.items()
                if key
                not in {
                    "matched_base_product_keys",
                    "match_types",
                }
            }
            | {
                "matched_base_product_keys": (
                    sorted(
                        variant[
                            "matched_base_product_keys"
                        ]
                    )
                ),
                "match_types": sorted(
                    variant["match_types"]
                ),
            }
            for variant in variants
        ],
        "competitor_product_keys": sorted({
            int(variant["product_key"])
            for variant in variants
            if variant.get("product_key") is not None
        }),
    }


# ============================================================
# SORTING
# ============================================================


def market_card_sort_key(
    card: dict,
):
    """
    Сортировка по умолчанию:

    1. максимальное совпадение характеристик;
    2. участвует в выбранном snapshot;
    3. смэчен с открытым товаром;
    4. смэчен хотя бы с одним нашим товаром;
    5. source;
    6. product_key.
    """

    return (
        -int(
            card["is_used_in_snapshot"]
        ),
        -int(
            card["is_matched_current"]
        ),
        -int(
            card["is_matched_any"]
        ),
        (
            card["source"]
            or ""
        ).casefold(),
        card["product_key"],
    )


# ============================================================
# MAIN SERVICE
# ============================================================


def build_iprice_market_assortment(
    *,
    snapshot_product: IPriceSnapshotProduct,
) -> dict:
    """
    Формирует справочный рыночный ассортимент
    для одного нашего товара snapshot.

    Важно:

    - эти товары не добавляются в snapshot;
    - они не участвуют в медиане конкурентов;
    - они не участвуют в расчёте РРЦ;
    - результат строится по текущей активной
      ParserProductClassification.

    Основной отбор:

        category
        subcategory
        subcategory_type
        item_type

    Отображаются все активные конкурентные товары того же класса. Оценка
    matching и прохождение порогов отражаются информационно.
    """

    classifications = (
        get_market_classifications(
            snapshot_product=(
                snapshot_product
            )
        )
    )


    if not classifications:
        return {
            "snapshot_id": (
                snapshot_product.snapshot_id
            ),
            "snapshot_product_id": (
                snapshot_product.id
            ),
            "base_product_key": (
                snapshot_product
                .base_product_key
            ),
            "selection": {
                "category": (
                    snapshot_product.category
                ),
                "subcategory": (
                    snapshot_product
                    .subcategory
                ),
                "subcategory_type": (
                    snapshot_product
                    .subcategory_type
                ),
                "item_type": (
                    snapshot_product.item_type
                ),
            },
            "counts": {
                "cards": 0,
                "regional_variants": 0,
                "used_in_snapshot": 0,
                "matched_current": 0,
                "matched_any": 0,
                "not_matched": 0,
            },
            "results": [],
        }

    classification_keys = {
        classification.product_key
        for classification
        in classifications
    }

    # Нужны только активные конкурентные URL.
    url_rows = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=classification_keys,
                status=(
                    ParserProductUrl
                    .STATUS_ACTIVE
                ),
            )
            .exclude(
                source="base",
            )
            .values(
                "id",
                "source",
                "prefix",
                "url",
                "additional_property",
            )
        )
    }

    competitor_product_keys = set(
        url_rows
    )

    if not competitor_product_keys:
        return {
            "snapshot_id": (
                snapshot_product.snapshot_id
            ),
            "snapshot_product_id": (
                snapshot_product.id
            ),
            "base_product_key": (
                snapshot_product
                .base_product_key
            ),
            "selection": {
                "category": (
                    snapshot_product.category
                ),
                "subcategory": (
                    snapshot_product
                    .subcategory
                ),
                "subcategory_type": (
                    snapshot_product
                    .subcategory_type
                ),
                "item_type": (
                    snapshot_product.item_type
                ),
            },
            "counts": {
                "cards": 0,
                "regional_variants": 0,
                "used_in_snapshot": 0,
                "matched_current": 0,
                "matched_any": 0,
                "not_matched": 0,
            },
            "results": [],
        }

    classifications_by_key = {
        classification.product_key: (
            classification
        )
        for classification
        in classifications
        if (
            classification.product_key
            in competitor_product_keys
        )
    }

    group_key_by_product = (
        build_market_group_key_map(
            competitor_product_keys=(
                competitor_product_keys
            )
        )
    )

    match_data = get_match_data(
        competitor_product_keys=(
            competitor_product_keys
        ),
        current_base_product_key=(
            snapshot_product
            .base_product_key
        ),
    )

    snapshot_competitor_keys = (
        get_snapshot_competitor_keys(
            snapshot_product=(
                snapshot_product
            )
        )
    )

    prefix_region_map = (
        build_prefix_region_map()
    )

    calculation_date = (
        snapshot_product
        .snapshot
        .calculation_date
    )
    price_data_by_product = {
        product_key: get_competitor_price_data(
            product_key=product_key,
            calculation_date=calculation_date,
        )
        for product_key
        in competitor_product_keys
    }

    variants_by_group = defaultdict(list)

    for product_key in sorted(
        competitor_product_keys
    ):
        classification = (
            classifications_by_key.get(
                product_key
            )
        )

        url_row = url_rows.get(
            product_key
        )

        group_key = (
            group_key_by_product.get(
                product_key
            )
        )

        if (
            classification is None
            or url_row is None
            or group_key is None
        ):
            continue

        source = clean_text(
            url_row["source"]
        )

        prefix = clean_text(
            url_row["prefix"]
        )

        match_item = match_data.get(
            product_key,
            {
                "is_matched_any": False,
                "is_matched_current": False,
                "matched_base_product_keys": (
                    set()
                ),
                "match_types": set(),
            },
        )

        variants_by_group[
            group_key
        ].append({
            "product_key": product_key,
            "source": source,
            "prefix": prefix,

            "category": (
                classification.category
            ),
            "subcategory": (
                classification.subcategory
            ),
            "subcategory_type": (
                classification
                .subcategory_type
            ),
            "item_type": (
                classification.item_type
            ),

            "material": (
                classification.material
            ),
            "color": (
                classification.color
            ),
            "modification": (
                classification.modification
            ),
            "article_number_analogs": classification.article_number_analogs,
            "additional_property": (
                price_data_by_product[product_key].get("additional_property")
                if price_data_by_product[product_key]
                else url_row.get("additional_property")
            ),

            # Берём собственные значения
            # конкретного product_key.
            "url": (
                classification.url
                or url_row["url"]
            ),
            "image": (
                classification.image
            ),
            "name": (
                price_data_by_product[product_key]["variants"][0].get("name")
                if price_data_by_product[product_key]
                and price_data_by_product[product_key].get("variants")
                else None
            ),
            "price_variants": (
                [
                    {
                        **price_variant,
                        "is_selected_price_row": (
                            price_data_by_product[product_key].get(
                                "calculation_row_id"
                            ) is not None
                            and price_variant.get("id")
                            == price_data_by_product[product_key].get(
                                "calculation_row_id"
                            )
                        ),
                    }
                    for price_variant in price_data_by_product[product_key].get(
                        "variants", []
                    )
                ]
                if price_data_by_product[product_key]
                else []
            ),
            "price": (
                price_data_by_product[
                    product_key
                ]["calculation_price"]
                if price_data_by_product[
                    product_key
                ]
                else None
            ),
            "is_price_used_in_calculation": (
                price_data_by_product[product_key] is not None
                and positive_price_or_none(
                    price_data_by_product[product_key]["calculation_price"]
                ) is not None
            ),


            "is_matched_any": (
                match_item[
                    "is_matched_any"
                ]
            ),
            "is_matched_current": (
                match_item[
                    "is_matched_current"
                ]
            ),
            "is_used_in_snapshot": (
                product_key
                in snapshot_competitor_keys
            ),

            "matched_base_product_keys": (
                match_item[
                    "matched_base_product_keys"
                ]
            ),
            "match_types": (
                match_item["match_types"]
            ),

            "regions": get_url_regions(
                source=source,
                prefix=prefix,
                prefix_region_map=(
                    prefix_region_map
                ),
            ),
        })

    cards = [
        build_market_card(
            group_key=group_key,
            variants=variants,
        )
        for group_key, variants
        in variants_by_group.items()
        if variants
    ]

    cards.sort(
        key=market_card_sort_key
    )

    return {
        "snapshot_id": (
            snapshot_product.snapshot_id
        ),
        "snapshot_product_id": (
            snapshot_product.id
        ),
        "base_product_key": (
            snapshot_product
            .base_product_key
        ),

        "selection": {
            "category": (
                snapshot_product.category
            ),
            "subcategory": (
                snapshot_product
                .subcategory
            ),
            "subcategory_type": (
                snapshot_product
                .subcategory_type
            ),
            "item_type": (
                snapshot_product.item_type
            ),

            "material": (
                snapshot_product.material
            ),
            "color": (
                snapshot_product.color
            ),
            "modification": (
                snapshot_product
                .modification
            ),
        },

        "counts": {
            "cards": len(cards),

            "regional_variants": sum(
                card[
                    "regional_variants_count"
                ]
                for card in cards
            ),

            "used_in_snapshot": sum(
                card[
                    "is_used_in_snapshot"
                ]
                for card in cards
            ),

            "matched_current": sum(
                card[
                    "is_matched_current"
                ]
                for card in cards
            ),

            "matched_any": sum(
                card["is_matched_any"]
                for card in cards
            ),

            "not_matched": sum(
                not card["is_matched_any"]
                for card in cards
            ),
        },

        "results": cards,
    }


def group_snapshot_competitor_cards(items: list[dict]) -> list[dict]:
    """Объединяет региональные копии конкурента как рыночный ассортимент."""
    if not items:
        return []

    group_keys = build_market_group_key_map(
        competitor_product_keys={
            int(item["competitor_product_key"])
            for item in items
            if item.get("competitor_product_key") is not None
        },
    )
    grouped = defaultdict(list)
    for item in items:
        product_key = item.get("competitor_product_key")
        key = group_keys.get(product_key) or (
            "single",
            normalized_text(item.get("source")) or "",
            product_key,
        )
        grouped[key].append(item)

    result = []
    for group_key, competitors in grouped.items():
        representative = next(
            (
                item for item in competitors
                if any(
                    variant.get("image")
                    for variant in (item.get("price_variants") or [])
                )
            ),
            competitors[0],
        )
        prices = []
        for item in competitors:
            value = item.get("competitor_final_price_max")
            if value is None:
                continue
            try:
                normalized_price = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if normalized_price <= 0:
                continue
            prices.append(normalized_price)
        regional_entries = []
        seen_entries = set()
        all_variants = []
        applicable_regions_by_key = {}
        is_all_regions = False
        for item in competitors:
            is_all_regions = is_all_regions or bool(
                item.get("is_all_regions")
            )
            for applicable_region in item.get("applicable_regions") or []:
                normalized_region = clean_text(applicable_region)
                if normalized_region:
                    applicable_regions_by_key[
                        normalized_region.casefold()
                    ] = normalized_region
            item_variants = item.get("price_variants") or []
            selected_price_row_id = item.get("source_price_row_id")
            all_variants.extend(
                {
                    **variant,
                    "is_selected_price_row": (
                        selected_price_row_id is not None
                        and variant.get("id") == selected_price_row_id
                    ),
                }
                for variant in item_variants
            )
            market_regions = []
            for variant in item_variants:
                market_regions.extend(variant.get("market_regions") or [])
            regions = list(dict.fromkeys(market_regions)) or item.get(
                "applicable_regions"
            ) or (
                ["Все регионы"] if item.get("is_all_regions") else []
            )
            if not regions:
                regions = ["Регион не определён"]
            for region in regions:
                entry_key = (
                    str(region).casefold(),
                    item.get("competitor_product_key"),
                )
                if entry_key in seen_entries:
                    continue
                seen_entries.add(entry_key)
                regional_entries.append({
                    "region": region,
                    "product_key": item.get("competitor_product_key"),
                    "price": item.get("competitor_final_price_max"),
                    "url": item.get("url"),
                })

        card = dict(representative)
        card.update({
            "group_key": "|".join(str(value) for value in group_key),
            "competitor_product_keys": sorted({
                item["competitor_product_key"]
                for item in competitors
                if item.get("competitor_product_key") is not None
            }),
            "competitor_final_price_median": (
                median(prices) if prices else None
            ),
            "is_price_used_in_calculation": bool(prices),
            "is_all_regions": is_all_regions,
            "applicable_regions": sorted(
                applicable_regions_by_key.values(),
                key=str.casefold,
            ),
            "price_variants": all_variants,
            "regional_entries": sorted(
                regional_entries,
                key=lambda entry: (
                    str(entry["region"]).casefold(),
                    entry["product_key"] or 0,
                ),
            ),
        })
        result.append(card)

    return sorted(
        result,
        key=lambda item: (
            str(item.get("source") or "").casefold(),
            str(item.get("group_key") or ""),
        ),
    )
