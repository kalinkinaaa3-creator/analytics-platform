from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone

from datasets.models import (
    BaseProductPrice,
    DepartureDiscount,
    IPriceCalculationConfig,
    NomenclaturePrice,
    ParserPrefix,
    ParserProductUrl,
    ProductCost,
    PsProductPrice,
    TaraProductPrice,
    TransportCost,
    TtProductPrice,
)


COMPETITOR_PRICE_MODELS = {
    "tara": TaraProductPrice,
    "ps": PsProductPrice,
    "tt": TtProductPrice,
}


def get_local_date(value) -> date | None:
    """
    Преобразует DateTimeField в локальную календарную дату.
    """

    if value is None:
        return None

    if timezone.is_aware(value):
        value = timezone.localtime(value)

    return value.date()


def is_today(calculation_date: date) -> bool:
    """
    Проверяет, является ли расчетная дата сегодняшним днем.

    Для сегодняшнего расчета используются только активные записи.
    Для прошлого периода используются исторические записи,
    существовавшие не позднее calculation_date.
    """

    return calculation_date == timezone.localdate()


def decimal_to_string(
    value,
) -> str | None:
    """
    Decimal нельзя безопасно хранить в JSONField напрямую
    во всех сценариях, поэтому сохраняем строкой.
    """

    if value is None:
        return None

    return str(value)


def positive_price_or_none(value):
    if value is None:
        return None
    return value if value > 0 else None


def get_iprice_config(
    *,
    product_key: int,
    departure: str,
    arrival: str,
    calculation_date: date,
) -> IPriceCalculationConfig | None:
    """
    Возвращает конфигурацию расчета iPrice.

    Текущий день:
        используется только is_active=True.

    Прошлая дата:
        используется последняя запись с
        DATE(date_add) <= calculation_date.

    Исторический расчет использует последнюю конфигурацию,
    существовавшую на выбранную дату, независимо от ее
    текущего is_active.
    """

    queryset = IPriceCalculationConfig.objects.filter(
        product_key=product_key,
        departure__iexact=normalize_text(departure),
        arrival__iexact=normalize_text(arrival),
    )

    if is_today(calculation_date):
        return (
            queryset
            .filter(is_active=True)
            .order_by("-date_add", "-id")
            .first()
        )

    return (
        queryset
        .filter(
            date_add__date__lte=calculation_date,
        )
        .order_by("-date_add", "-id")
        .first()
    )


def get_departure_discount(
    *,
    product_key: int,
    departure: str,
    arrival: str,
    calculation_date: date,
) -> DepartureDiscount | None:
    """
    Возвращает скидки для товара и производства.

    Текущий день:
        используется активная запись.

    Прошлая дата:
        используется последняя версия,
        созданная не позднее calculation_date.
    """

    normalized_departure = normalize_text(departure)
    normalized_arrival = normalize_text(arrival)

    if not normalized_departure or not normalized_arrival:
        return None

    queryset = DepartureDiscount.objects.filter(
        product_key=product_key,
        departure__iexact=normalized_departure,
        arrival__iexact=normalized_arrival,
    )

    if is_today(calculation_date):
        return (
            queryset
            .filter(is_active=True)
            .order_by("-date_add", "-id")
            .first()
        )

    return (
        queryset
        .filter(
            date_add__date__lte=calculation_date,
        )
        .order_by("-date_add", "-id")
        .first()
    )


def get_transport_cost(
    *,
    departure: str,
    arrival: str,
    calculation_date: date,
) -> TransportCost | None:
    """
    Возвращает стоимость перевозки для маршрута.

    Текущий день:
        используется активная стоимость маршрута.

    Прошлая дата:
        используется последняя версия маршрута,
        созданная не позднее calculation_date.
    """

    normalized_departure = normalize_text(departure)
    normalized_arrival = normalize_text(arrival)

    if not normalized_departure or not normalized_arrival:
        return None

    queryset = TransportCost.objects.filter(
        departure__iexact=normalized_departure,
        arrival__iexact=normalized_arrival,
    )

    if is_today(calculation_date):
        return (
            queryset
            .filter(is_active=True)
            .order_by("-date_add", "-id")
            .first()
        )

    return (
        queryset
        .filter(
            date_add__date__lte=calculation_date,
        )
        .order_by("-date_add", "-id")
        .first()
    )


def normalize_text(value: str | None) -> str | None:
    """
    Выполняет минимальную нормализацию строковых ключей.

    Не меняет структуру названия города или производства,
    поскольку first_word уже применяется в загрузчиках.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def get_product_cost(
    *,
    code: int,
    departure: str,
    calculation_date: date,
) -> ProductCost | None:
    """
    Возвращает себестоимость товара за месяц расчета.

    Себестоимость хранится с датой первого числа месяца.

    Например:
        calculation_date = 2026-07-31
        cost_month = 2026-07-01

    Fallback на предыдущий месяц не используется.
    """

    normalized_departure = normalize_text(
        departure
    )

    if not normalized_departure:
        return None

    cost_month = calculation_date.replace(
        day=1
    )

    return (
        ProductCost.objects
        .filter(
            date=cost_month,
            code=code,
            departure__iexact=normalized_departure,
        )
        .order_by(
            "-id",
        )
        .first()
    )


def get_nomenclature_price(
    *,
    code: int,
    shipp_region: str,
    calculation_date: date,
) -> NomenclaturePrice | None:
    """
    Возвращает последнюю цену 1С для кода и региона.

    Правило:
        MAX(date)
        WHERE date <= calculation_date
    """

    normalized_region = normalize_text(
        shipp_region
    )

    if not normalized_region:
        return None

    return (
        NomenclaturePrice.objects
        .filter(
            code=code,
            shipp_region__iexact=normalized_region,
            date__lte=calculation_date,
        )
        .order_by(
            "-date",
            "-id",
        )
        .first()
    )


def get_nomenclature_prices_by_region(
    *,
    code: int,
    calculation_date: date,
) -> dict[str, NomenclaturePrice]:
    """
    Возвращает по одной последней цене для каждого региона.

    Результат:
        {
            "москва": NomenclaturePrice(...),
            "казань": NomenclaturePrice(...),
        }

    Ключ словаря нормализован через casefold().
    """

    rows = (
        NomenclaturePrice.objects
        .filter(
            code=code,
            date__lte=calculation_date,
        )
        .exclude(
            shipp_region__isnull=True,
        )
        .exclude(
            shipp_region="",
        )
        .order_by(
            "shipp_region",
            "-date",
            "-id",
        )
    )

    result = {}

    for row in rows:
        region = normalize_text(
            row.shipp_region
        )

        if not region:
            continue

        region_key = region.casefold()

        if region_key in result:
            continue

        result[region_key] = row

    return result


def get_competitor_price_data(
    *,
    product_key: int,
    calculation_date: date,
) -> dict[str, Any] | None:
    """
    Возвращает конкурентные цены за последний доступный день.

    Алгоритм:

    1. Определить source через ParserProductUrl.
    2. Выбрать соответствующую price-модель.
    3. Найти максимальный календарный день date_add с
       положительной final_price, не превышающий calculation_date.
    4. Сохранить все строки этого дня как variants.
    5. Для расчета выбрать MAX(final_price).
    6. Если положительной цены нет, вернуть информационные варианты
       последнего доступного дня с calculation_price=None. Они нужны для
       изображения и свойств карточки, но в расчёте не участвуют.

    Если URL, модель источника или любые строки товара отсутствуют,
    возвращается None.
    """

    product_url = (
        ParserProductUrl.objects
        .filter(
            id=product_key,
        )
        .only(
            "id",
            "source",
            "url",
            "prefix",
            "additional_property",
        )
        .first()
    )

    if product_url is None:
        return None

    source = normalize_text(
        product_url.source
    )

    if not source:
        return None

    source_key = source.casefold()

    price_model = COMPETITOR_PRICE_MODELS.get(
        source_key
    )

    if price_model is None:
        return None

    base_queryset = price_model.objects.filter(
        product_key=product_key,
        date_add__date__lte=calculation_date,
    )
    latest_positive_row = (
        base_queryset.filter(final_price__gt=0)
        .order_by("-date_add", "-id")
        .first()
    )
    latest_any_row = latest_positive_row or (
        base_queryset.order_by("-date_add", "-id").first()
    )
    if latest_any_row is None or latest_any_row.date_add is None:
        return None

    latest_day = get_local_date(latest_any_row.date_add)
    latest_rows_queryset = base_queryset.filter(date_add__date=latest_day)
    if latest_positive_row is not None:
        latest_rows_queryset = latest_rows_queryset.filter(final_price__gt=0)
    latest_rows = list(latest_rows_queryset.order_by("id"))

    valid_final_prices = [
        row.final_price
        for row in latest_rows
        if positive_price_or_none(row.final_price) is not None
    ]

    calculation_price = (
        max(valid_final_prices)
        if valid_final_prices
        else None
    )

    variants = [
        serialize_competitor_price_row(
            row=row,
            source=source_key,
        )
        for row in latest_rows
    ]

    calculation_row = None

    if calculation_price is not None:
        calculation_row = min(
            (
                row
                for row in latest_rows
                if row.final_price == calculation_price
            ),
            key=lambda row: row.id,
        )

    return {
        "product_key": product_key,
        "source": source_key,
        "price_date": latest_day,
        "calculation_price": calculation_price,
        "calculation_row_id": (
            calculation_row.id
            if calculation_row
            else None
        ),
        "variants": variants,
        "product_url_id": product_url.id,
        "url": product_url.url,
        "prefix": product_url.prefix,
        "additional_property": (
            product_url.additional_property
        ),
    }


def serialize_competitor_price_row(
    *,
    row,
    source: str,
) -> dict[str, Any]:
    """
    Преобразует строку конкурентной цены в JSON-совместимый dict.

    Не все модели имеют одинаковый состав полей,
    поэтому необязательные значения получаем через getattr().
    """

    return {
        "id": row.id,
        "source": source,
        "product_key": row.product_key,
        "date_add": (
            row.date_add.isoformat()
            if row.date_add
            else None
        ),
        "price": decimal_to_string(
            positive_price_or_none(getattr(row, "price", None))
        ),
        "value_added_tax": decimal_to_string(
            getattr(
                row,
                "value_added_tax",
                None,
            )
        ),
        "final_price": decimal_to_string(
            positive_price_or_none(getattr(row, "final_price", None))
        ),
        "name": getattr(
            row,
            "name",
            None,
        ),
        "url": getattr(
            row,
            "url",
            None,
        ),
        "color": getattr(
            row,
            "color",
            None,
        ),
        "image": getattr(
            row,
            "image",
            None,
        ),
        "properties_price": getattr(
            row,
            "properties_price",
            None,
        ),
        "additional_property": getattr(
            row,
            "additional_property",
            None,
        ),
        "special_quantity": getattr(
            row,
            "special_quantity",
            None,
        ),
        "category": getattr(
            row,
            "category",
            None,
        ),
        "discount": getattr(
            row,
            "discount",
            None,
        ),
    }


def get_base_product_price(
    *,
    product_key: int,
    calculation_date: date,
) -> BaseProductPrice | None:
    """
    Возвращает актуальную строку нашего товара на дату расчета.

    Правило:
    1. Максимальный календарный день date_add,
       не превышающий calculation_date.
    2. За этот день:
       - сначала строки с заполненным code_1c;
       - затем максимальная final_price;
       - при равенстве — минимальный id.
    """

    rows = list(
        BaseProductPrice.objects
        .filter(
            product_key=product_key,
            date_add__date__lte=calculation_date,
        )
        .order_by(
            "-date_add",
            "-id",
        )
    )

    if not rows:
        return None

    latest_day = max(
        get_local_date(row.date_add)
        for row in rows
        if row.date_add is not None
    )

    latest_rows = [
        row
        for row in rows
        if get_local_date(row.date_add) == latest_day
    ]

    rows_with_code = [
        row
        for row in latest_rows
        if row.code_1c is not None
    ]

    if not rows_with_code:
        return None

    rows_with_final_price = [
        row
        for row in rows_with_code
        if row.final_price is not None
    ]

    if rows_with_final_price:
        max_final_price = max(
            row.final_price
            for row in rows_with_final_price
        )
        return min(
            (
                row
                for row in rows_with_final_price
                if row.final_price == max_final_price
            ),
            key=lambda row: row.id,
        )

    return min(
        rows_with_code,
        key=lambda row: row.id,
    )


def split_regions(
    value: str | None,
) -> list[str]:
    """
    Разбирает несколько регионов, разделенных точкой с запятой.

    Например:
        "Москва;Ставрово"
        ->
        ["Москва", "Ставрово"]
    """

    normalized_value = normalize_text(value)

    if not normalized_value:
        return []

    result = []

    for part in normalized_value.split(";"):
        region = normalize_text(part)

        if (
            region
            and region != "-"
        ):
            result.append(region)

    return result


def get_all_sale_regions() -> list[str]:
    """
    Возвращает уникальные регионы продажи из ParserPrefix.

    NomenclaturePrice не является источником списка регионов.
    """

    result_by_key = {}

    values = (
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

    for value in values:
        for region in split_regions(value):
            key = region.casefold()

            if key not in result_by_key:
                result_by_key[key] = region

    return sorted(
        result_by_key.values(),
        key=str.casefold,
    )


def get_competitor_regions(
    *,
    source: str,
    prefix: str | None,
) -> dict[str, Any]:
    """
    Определяет региональную применимость конкурента.

    Если по source вообще нет регионов в ParserPrefix:
        конкурент применяется ко всем регионам.

    Если prefix == "-":
        конкурент также применяется ко всем регионам.

    Иначе используются регионы строк
    ParserPrefix для конкретного source + prefix.
    """

    normalized_source = normalize_text(source)
    normalized_prefix = normalize_text(prefix)

    if not normalized_source:
        return {
            "is_all_regions": True,
            "regions": [],
            "region_groups": [],
        }

    source_rows = list(
        ParserPrefix.objects
        .filter(
            source__iexact=normalized_source,
        )
        .values(
            "prefix",
            "shipp_region",
        )
    )

    source_regions = []

    for row in source_rows:
        source_regions.extend(
            split_regions(
                row["shipp_region"]
            )
        )

    # У источника нет настроенной региональной разбивки.
    if not source_regions:
        return {
            "is_all_regions": True,
            "regions": [],
            "region_groups": [],
        }

    if (
        not normalized_prefix
        or normalized_prefix == "-"
    ):
        return {
            "is_all_regions": True,
            "regions": [],
            "region_groups": [],
        }

    prefix_regions_by_key = {}
    region_groups_by_key = {}

    for row in source_rows:
        row_prefix = normalize_text(
            row["prefix"]
        )

        if (
            not row_prefix
            or row_prefix.casefold()
            != normalized_prefix.casefold()
        ):
            continue

        region_group = normalize_text(row["shipp_region"])
        if region_group:
            normalized_group = ";".join(
                split_regions(region_group)
            )
            if normalized_group:
                region_groups_by_key[
                    normalized_group.casefold()
                ] = normalized_group

        for region in split_regions(
            row["shipp_region"]
        ):
            prefix_regions_by_key[
                region.casefold()
            ] = region

    return {
        "is_all_regions": False,
        "regions": sorted(
            prefix_regions_by_key.values(),
            key=str.casefold,
        ),
        "region_groups": sorted(
            region_groups_by_key.values(),
            key=str.casefold,
        ),
    }
