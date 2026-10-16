from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Count, Q, QuerySet

from datasets.models import (
    IPriceSnapshot,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
)


MODE_PRODUCTS = "products"
MODE_REGIONS = "regions"

FILTER_TYPE_TEXT = "text"
FILTER_TYPE_INTEGER = "integer"


# ============================================================
# FILTER FIELD MAPS
# ============================================================


PRODUCT_FILTER_FIELDS = {
    # Основные идентификаторы товара.
    "code_1c": "code_1c",
    "nom": "nom",
    "base_product_key": "base_product_key",

    # Расчётные признаки.
    "pricing_method": "pricing_method",
    "calculation_status": "calculation_status",
    "assortment_matrix_status": (
        "assortment_matrix_status"
    ),
    "our_offer": "our_offer",

    # Номенклатурная классификация 1С.
    "nom_hier_code": "nom_hier_code",
    "nom_hier": "nom_hier",
    "nom_view": "nom_view",
    "nom_category": "nom_category",
    "nom_group": "nom_group",

    # Внутренняя классификация.
    "category": "category",
    "subcategory": "subcategory",
    "subcategory_type": "subcategory_type",

    # Информационные свойства товара.
    "color": "color",
    "material": "material",
    "modification": "modification",
}


REGION_FILTER_FIELDS = {
    # Основные идентификаторы товара.
    "code_1c": (
        "snapshot_product__code_1c"
    ),
    "nom": (
        "snapshot_product__nom"
    ),
    "base_product_key": (
        "snapshot_product__base_product_key"
    ),

    # Расчётные признаки.
    "pricing_method": (
        "snapshot_product__pricing_method"
    ),
    "calculation_status": (
        "calculation_status"
    ),
    "assortment_matrix_status": (
        "snapshot_product__"
        "assortment_matrix_status"
    ),
    "our_offer": (
        "snapshot_product__our_offer"
    ),

    # Региональная гранулярность.
    "sale_region": "sale_region",
    "departure": "departure",

    # Номенклатурная классификация 1С.
    "nom_hier_code": (
        "snapshot_product__nom_hier_code"
    ),
    "nom_hier": (
        "snapshot_product__nom_hier"
    ),
    "nom_view": (
        "snapshot_product__nom_view"
    ),
    "nom_category": (
        "snapshot_product__nom_category"
    ),
    "nom_group": (
        "snapshot_product__nom_group"
    ),

    # Внутренняя классификация.
    "category": (
        "snapshot_product__category"
    ),
    "subcategory": (
        "snapshot_product__subcategory"
    ),
    "subcategory_type": (
        "snapshot_product__subcategory_type"
    ),

    # Информационные свойства товара.
    "color": (
        "snapshot_product__color"
    ),
    "material": (
        "snapshot_product__material"
    ),
    "modification": (
        "snapshot_product__modification"
    ),
}


# Тип значения нужен, чтобы числовые поля
# не сравнивались через текстовый __iexact.
PRODUCT_FILTER_TYPES = {
    "code_1c": FILTER_TYPE_INTEGER,
    "base_product_key": FILTER_TYPE_INTEGER,
}


REGION_FILTER_TYPES = {
    "code_1c": FILTER_TYPE_INTEGER,
    "base_product_key": FILTER_TYPE_INTEGER,
}


PRODUCT_FILTER_ORDER = (
    # Идентификация товара.
    "code_1c",
    "nom",
    "base_product_key",

    # Расчёт.
    "pricing_method",
    "calculation_status",
    "assortment_matrix_status",
    "our_offer",

    # Номенклатура 1С.
    "nom_hier_code",
    "nom_hier",
    "nom_view",
    "nom_category",
    "nom_group",

    # Внутренняя классификация.
    "category",
    "subcategory",
    "subcategory_type",

    # Свойства.
    "color",
    "material",
    "modification",
)


REGION_FILTER_ORDER = (
    # Идентификация товара.
    "code_1c",
    "nom",
    "base_product_key",

    # Расчёт.
    "pricing_method",
    "calculation_status",
    "assortment_matrix_status",
    "our_offer",

    # Регион.
    "sale_region",
    "departure",

    # Номенклатура 1С.
    "nom_hier_code",
    "nom_hier",
    "nom_view",
    "nom_category",
    "nom_group",

    # Внутренняя классификация.
    "category",
    "subcategory",
    "subcategory_type",

    # Свойства.
    "color",
    "material",
    "modification",
)


# ============================================================
# NORMALIZATION
# ============================================================


def normalize_filter_values(
    values,
) -> list[str]:
    """
    Нормализует значения одного множественного фильтра.

    Правила:
    - значение приводится к строке;
    - пустые значения удаляются;
    - дубли удаляются без учёта регистра;
    - исходный порядок сохраняется.
    """

    if values is None:
        return []

    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        values = [values]

    elif not isinstance(
        values,
        Iterable,
    ):
        return []

    result = []
    seen = set()

    for value in values:
        if value is None:
            continue

        normalized_value = str(
            value
        ).strip()

        if not normalized_value:
            continue

        value_key = (
            normalized_value.casefold()
        )

        if value_key in seen:
            continue

        seen.add(value_key)

        result.append(
            normalized_value
        )

    return result


def normalize_filters(
    *,
    filters: dict | None,
    allowed_fields: dict[str, str],
) -> dict[str, list[str]]:
    """
    Оставляет только разрешённые фильтры
    и нормализует их значения.
    """

    filters = filters or {}

    if not isinstance(filters, dict):
        return {}

    result = {}

    for filter_name in allowed_fields:
        values = normalize_filter_values(
            filters.get(
                filter_name,
                [],
            )
        )

        if values:
            result[filter_name] = values

    return result


def normalize_integer_values(
    values: list[str],
) -> list[int]:
    """
    Преобразует значения числового фильтра в int.

    Невалидные значения пропускаются.
    Дубли удаляются с сохранением порядка.
    """

    result = []
    seen = set()

    for value in values:
        try:
            integer_value = int(
                str(value).strip()
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if integer_value in seen:
            continue

        seen.add(integer_value)
        result.append(integer_value)

    return result


# ============================================================
# MULTI-VALUE FILTERING
# ============================================================


def apply_multi_value_filter(
    *,
    queryset: QuerySet,
    model_field: str,
    values: list[str],
    filter_type: str = FILTER_TYPE_TEXT,
) -> QuerySet:
    """
    Применяет один множественный фильтр.

    Внутри одного фильтра используется OR:

        category = A OR category = B

    Между разными фильтрами используется AND,
    поскольку фильтры применяются последовательно.

    Для числовых полей используется __in.
    Для текстовых — набор сравнений __iexact.
    """

    if not values:
        return queryset

    if filter_type == FILTER_TYPE_INTEGER:
        integer_values = (
            normalize_integer_values(
                values
            )
        )

        if not integer_values:
            return queryset.none()

        return queryset.filter(
            **{
                f"{model_field}__in": (
                    integer_values
                ),
            }
        )

    filter_query = Q()

    for value in values:
        filter_query |= Q(
            **{
                f"{model_field}__iexact": (
                    value
                ),
            }
        )

    return queryset.filter(
        filter_query
    )


def apply_dependent_filters(
    *,
    queryset: QuerySet,
    filters: dict[str, list[str]],
    field_map: dict[str, str],
    type_map: dict[str, str] | None = None,
    excluded_filter: str | None = None,
) -> QuerySet:
    """
    Применяет все выбранные фильтры.

    Если указан excluded_filter, его собственное
    значение не применяется. Это требуется при
    формировании зависимого списка этого фильтра.

    Например, при формировании вариантов category:

    - выбранный material применяется;
    - выбранный sale_region применяется;
    - выбранная category временно не применяется.
    """

    type_map = type_map or {}

    for filter_name, values in (
        filters.items()
    ):
        if filter_name == excluded_filter:
            continue

        model_field = field_map.get(
            filter_name
        )

        if not model_field:
            continue

        queryset = apply_multi_value_filter(
            queryset=queryset,
            model_field=model_field,
            values=values,
            filter_type=type_map.get(
                filter_name,
                FILTER_TYPE_TEXT,
            ),
        )

    return queryset


# ============================================================
# PUBLIC QUERYSET FILTERS
# ============================================================


def filter_iprice_products_queryset(
    *,
    queryset: QuerySet,
    filters: dict | None,
) -> QuerySet:
    """
    Применяет множественные фильтры
    к строкам режима products.
    """

    if queryset.model._meta.app_label == 'select_market':
        from select_market.iprice_filters import PRODUCT_FILTERS, filter_products
        queryset = filter_products(queryset, {key: value for key, value in (filters or {}).items() if key in PRODUCT_FILTERS})
        filters = {key: value for key, value in (filters or {}).items() if key not in PRODUCT_FILTERS}
    normalized_filters = normalize_filters(
        filters=filters,
        allowed_fields=(
            PRODUCT_FILTER_FIELDS
        ),
    )

    return apply_dependent_filters(
        queryset=queryset,
        filters=normalized_filters,
        field_map=PRODUCT_FILTER_FIELDS,
        type_map={**PRODUCT_FILTER_TYPES, 'code_1c': FILTER_TYPE_TEXT} if queryset.model._meta.app_label == 'select_market' else PRODUCT_FILTER_TYPES,
    )


def filter_iprice_regions_queryset(
    *,
    queryset: QuerySet,
    filters: dict | None,
) -> QuerySet:
    """
    Применяет множественные фильтры
    к строкам режима regions.
    """

    if queryset.model._meta.app_label == 'select_market':
        from select_market.iprice_filters import PRODUCT_FILTERS, filter_products
        queryset = filter_products(queryset, {key: value for key, value in (filters or {}).items() if key in PRODUCT_FILTERS}, prefix='snapshot_product__')
        filters = {key: value for key, value in (filters or {}).items() if key not in PRODUCT_FILTERS}
    normalized_filters = normalize_filters(
        filters=filters,
        allowed_fields=(
            REGION_FILTER_FIELDS
        ),
    )

    return apply_dependent_filters(
        queryset=queryset,
        filters=normalized_filters,
        field_map=REGION_FILTER_FIELDS,
        type_map={**REGION_FILTER_TYPES, 'code_1c': FILTER_TYPE_TEXT} if queryset.model._meta.app_label == 'select_market' else REGION_FILTER_TYPES,
    )


# ============================================================
# SEARCH
# ============================================================


def apply_iprice_products_search(
    *,
    queryset: QuerySet,
    search: str | None,
) -> QuerySet:
    """
    Общий текстовый поиск в режиме products.

    Отдельные точные фильтры code_1c, nom и
    base_product_key работают независимо от него.
    """

    search = str(
        search or ""
    ).strip()

    if not search:
        return queryset

    return queryset.filter(
        Q(
            nom__icontains=search
        )
        | Q(
            code_1c__icontains=search
        )
    )


def apply_iprice_regions_search(
    *,
    queryset: QuerySet,
    search: str | None,
) -> QuerySet:
    """
    Общий текстовый поиск в режиме regions.

    Отдельные точные фильтры code_1c, nom и
    base_product_key работают независимо от него.
    """

    search = str(
        search or ""
    ).strip()

    if not search:
        return queryset

    return queryset.filter(
        Q(
            snapshot_product__nom__icontains=(
                search
            )
        )
        | Q(
            snapshot_product__code_1c__icontains=(
                search
            )
        )
    )


# ============================================================
# DEPENDENT FILTER OPTIONS
# ============================================================


def build_filter_options(
    *,
    base_queryset: QuerySet,
    filters: dict[str, list[str]],
    filter_name: str,
    model_field: str,
    field_map: dict[str, str],
    type_map: dict[str, str] | None = None,
) -> list[dict]:
    """
    Формирует варианты одного зависимого фильтра.

    Применяются все выбранные фильтры,
    кроме самого формируемого фильтра.

    Поэтому пользователь может выбрать несколько
    значений одного поля, и список вариантов не
    схлопывается до уже выбранных значений.
    """

    type_map = type_map or {}

    filter_type = type_map.get(
        filter_name,
        FILTER_TYPE_TEXT,
    )

    queryset = apply_dependent_filters(
        queryset=base_queryset,
        filters=filters,
        field_map=field_map,
        type_map=type_map,
        excluded_filter=filter_name,
    )

    queryset = queryset.exclude(
        **{
            f"{model_field}__isnull": True,
        }
    )

    # Исключение пустой строки применимо только
    # к текстовым полям. Для IntegerField условие
    # field="" формировать не нужно.
    if filter_type == FILTER_TYPE_TEXT:
        queryset = queryset.exclude(
            **{
                model_field: "",
            }
        )

    rows = (
        queryset
        .values(
            model_field
        )
        .annotate(
            option_count=Count(
                "id",
                distinct=True,
            )
        )
        .order_by(
            model_field
        )
    )

    options = []
    seen = set()

    for row in rows:
        raw_value = row.get(
            model_field
        )

        if raw_value is None:
            continue

        normalized_value = str(
            raw_value
        ).strip()

        if not normalized_value:
            continue

        if filter_type == FILTER_TYPE_INTEGER:
            value_key = normalized_value
        else:
            value_key = (
                normalized_value.casefold()
            )

        if value_key in seen:
            continue

        seen.add(value_key)

        options.append({
            # В API значения фильтров передаются
            # строками, даже если модельное поле
            # является числовым.
            "value": normalized_value,
            "label": normalized_value,
            "count": row["option_count"],
        })

    return options


def build_filter_collection(
    *,
    base_queryset: QuerySet,
    filters: dict | None,
    field_map: dict[str, str],
    type_map: dict[str, str] | None,
    filter_order: tuple[str, ...],
) -> dict:
    """
    Формирует все зависимые варианты фильтров
    одного режима без дублирования логики.
    """

    normalized_filters = normalize_filters(
        filters=filters,
        allowed_fields=field_map,
    )

    options = {}

    for filter_name in filter_order:
        model_field = field_map[
            filter_name
        ]

        options[filter_name] = (
            build_filter_options(
                base_queryset=base_queryset,
                filters=normalized_filters,
                filter_name=filter_name,
                model_field=model_field,
                field_map=field_map,
                type_map=type_map,
            )
        )

    return {
        "selected": normalized_filters,
        "options": options,
    }


# ============================================================
# MODE BUILDERS
# ============================================================


def build_products_filters(
    *,
    snapshot: IPriceSnapshot,
    filters: dict | None,
) -> dict:
    """
    Возвращает зависимые фильтры
    режима products.
    """

    base_queryset = (
        IPriceSnapshotProduct.objects
        .filter(
            snapshot=snapshot,
        )
    )

    return build_filter_collection(
        base_queryset=base_queryset,
        filters=filters,
        field_map=PRODUCT_FILTER_FIELDS,
        type_map=PRODUCT_FILTER_TYPES,
        filter_order=PRODUCT_FILTER_ORDER,
    )


def build_regions_filters(
    *,
    snapshot: IPriceSnapshot,
    filters: dict | None,
) -> dict:
    """
    Возвращает зависимые фильтры
    режима regions.
    """

    base_queryset = (
        IPriceSnapshotRegion.objects
        .filter(
            snapshot_product__snapshot=(
                snapshot
            ),
        )
    )

    return build_filter_collection(
        base_queryset=base_queryset,
        filters=filters,
        field_map=REGION_FILTER_FIELDS,
        type_map=REGION_FILTER_TYPES,
        filter_order=REGION_FILTER_ORDER,
    )


def build_iprice_snapshot_filters(
    *,
    snapshot: IPriceSnapshot,
    mode: str,
    filters: dict | None,
) -> dict:
    """
    Главная функция получения зависимых
    фильтров выбранного snapshot.
    """

    normalized_mode = str(
        mode or ""
    ).strip().casefold()

    if normalized_mode == MODE_PRODUCTS:
        result = build_products_filters(
            snapshot=snapshot,
            filters=filters,
        )

    elif normalized_mode == MODE_REGIONS:
        result = build_regions_filters(
            snapshot=snapshot,
            filters=filters,
        )

    else:
        raise ValueError(
            (
                "mode must be "
                "'products' or 'regions'"
            )
        )

    return {
        "snapshot_id": snapshot.id,
        "mode": normalized_mode,
        **result,
    }
