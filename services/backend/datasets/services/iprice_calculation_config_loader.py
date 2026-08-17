import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile

from django.db import transaction
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from datasets.models import (
    BaseProductPrice,
    DepartureDiscount,
    IPriceCalculationConfig,
    ParserProductClassification,
    ParserProductUrl,
    ProductCost,
    TransportCost,
)
from datasets.services.iprice_source_selector import get_all_sale_regions


logger = logging.getLogger("datasets")

REQUIRED_COLUMNS = (
    "product_key",
    "departure",
    "arrival",
    "base_analog",
    "base_exclusive",
    "minimum_margin",
    "distr",
    "distr_1",
    "small",
    "medium",
    "large",
)


def clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_header(value):
    value = clean_text(value)
    if value is None:
        return None
    return value.casefold().replace(" ", "_").replace("-", "_")


def normalize_key(value):
    value = clean_text(value)
    return value.casefold() if value else None


def clean_product_key(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if decimal_value != decimal_value.to_integral_value():
        return None
    result = int(decimal_value)
    return result if result > 0 else None


def clean_decimal(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    is_percent = False
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        value = value.replace("\xa0", "").replace(" ", "").replace(",", ".")
        if value.endswith("%"):
            is_percent = True
            value = value[:-1]
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result / Decimal("100") if is_percent else result


def validate_file_extension(file_obj):
    file_name = clean_text(getattr(file_obj, "name", None))
    if not file_name:
        raise ValueError("Не удалось определить имя загруженного файла")
    if Path(file_name).suffix.casefold() != ".xlsx":
        raise ValueError("Поддерживается только формат XLSX")


def build_header_map(header_row):
    header_map = {}
    for column_index, value in enumerate(header_row):
        header_name = normalize_header(value)
        if header_name is None:
            continue
        if header_name in header_map:
            raise ValueError(f"В Excel найден повторяющийся заголовок: {header_name}")
        header_map[header_name] = column_index
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in header_map
    ]
    if missing_columns:
        raise ValueError(
            "В Excel отсутствуют обязательные столбцы: "
            + ", ".join(missing_columns)
        )
    return header_map


def get_row_value(row, header_map, column_name):
    column_index = header_map[column_name]
    return row[column_index] if column_index < len(row) else None


def build_validation_context(product_keys):
    classifications = {
        row.product_key: row
        for row in ParserProductClassification.objects.filter(
            product_key__in=product_keys,
            status=ParserProductClassification.STATUS_ACTIVE,
        )
    }
    urls = {
        row.id: row
        for row in ParserProductUrl.objects.filter(id__in=product_keys)
    }

    code_by_product = {}
    price_rows = (
        BaseProductPrice.objects.filter(product_key__in=product_keys)
        .exclude(code_1c__isnull=True)
        .order_by("product_key", "-date_add", "-id")
        .values_list("product_key", "code_1c")
    )
    for product_key, code_1c in price_rows:
        code_by_product.setdefault(product_key, code_1c)

    arrivals = {
        normalize_key(value): value
        for value in get_all_sale_regions()
    }
    costs = {
        (code, normalize_key(departure)): departure
        for code, departure in ProductCost.objects.filter(
            code__in=set(code_by_product.values())
        ).values_list("code", "departure")
        if normalize_key(departure)
    }
    routes = {
        (normalize_key(departure), normalize_key(arrival))
        for departure, arrival in TransportCost.objects.filter(
            is_active=True,
        ).values_list("departure", "arrival")
        if normalize_key(departure) and normalize_key(arrival)
    }
    return {
        "classifications": classifications,
        "urls": urls,
        "code_by_product": code_by_product,
        "arrivals": arrivals,
        "costs": costs,
        "routes": routes,
    }


def validate_row(row, context):
    row_index = row["row_index"]
    product_key = row["product_key"]
    departure_key = normalize_key(row["departure"])
    arrival_key = normalize_key(row["arrival"])
    errors = []

    if product_key is None:
        errors.append("product_key должен быть положительным целым числом")
    if not departure_key or departure_key == "-":
        errors.append("departure должен быть заполнен и не равен '-'")
    if not arrival_key or arrival_key == "-":
        errors.append("arrival должен быть заполнен и не равен '-'")

    classification = context["classifications"].get(product_key)
    if product_key is not None and classification is None:
        errors.append("нет активной строки parser_product_classification")
    elif classification.item_type not in {
        ParserProductClassification.ITEM_TYPE_PRODUCT,
        ParserProductClassification.ITEM_TYPE_COMPONENT,
    }:
        errors.append("item_type в parser_product_classification некорректен")

    url = context["urls"].get(product_key)
    if product_key is not None and url is None:
        errors.append("product_key отсутствует в parser_product_url")
    elif url.status != ParserProductUrl.STATUS_ACTIVE:
        errors.append("parser_product_url не активен")
    elif normalize_key(url.source) != "base":
        errors.append("product_key не относится к базовому товару")

    code_1c = context["code_by_product"].get(product_key)
    if product_key is not None and code_1c is None:
        errors.append("для product_key не найден актуальный code_1c")
    elif departure_key and (code_1c, departure_key) not in context["costs"]:
        errors.append("не найдена себестоимость для code_1c + departure")

    if arrival_key and arrival_key not in context["arrivals"]:
        errors.append("arrival отсутствует в parser_prefix.shipp_region")

    if (
        departure_key
        and arrival_key
        and departure_key != arrival_key
        and (departure_key, arrival_key) not in context["routes"]
    ):
        errors.append("не найден активный маршрут departure + arrival")

    if row["base_analog"] is None or row["base_analog"] < 0:
        errors.append("base_analog должен быть числом не меньше 0")
    if row["base_exclusive"] is None or not Decimal("0") < row["base_exclusive"] < Decimal("1"):
        errors.append("base_exclusive должен быть больше 0 и меньше 1")
    if row["minimum_margin"] is None or not Decimal("0") <= row["minimum_margin"] < Decimal("1"):
        errors.append("minimum_margin должен быть не меньше 0 и меньше 1")
    for field_name in (
        "distr",
        "distr_1",
        "small",
        "medium",
        "large",
    ):
        value = row[field_name]
        if value is None or not Decimal("0") <= value < Decimal("1"):
            errors.append(
                f"{field_name} должен быть не меньше 0 и меньше 1"
            )

    if errors:
        raise ValueError(f"Ошибка в строке {row_index}: " + "; ".join(errors))

    row["departure"] = context["costs"][(code_1c, departure_key)]
    row["arrival"] = context["arrivals"][arrival_key]
    row["item_type"] = classification.item_type
    row["code_1c"] = code_1c


def read_config_rows_from_xlsx(file_obj):
    validate_file_extension(file_obj)
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        workbook = load_workbook(file_obj, read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, OSError, ValueError) as exc:
        raise ValueError("Файл не является корректным XLSX") from exc

    try:
        rows_iterator = workbook.active.iter_rows(values_only=True)
        try:
            header_map = build_header_map(next(rows_iterator))
        except StopIteration as exc:
            raise ValueError("Excel-файл пуст") from exc

        rows = []
        for row_index, values in enumerate(rows_iterator, start=2):
            if not any(value is not None and str(value).strip() for value in values):
                continue
            rows.append({
                "product_key": clean_product_key(get_row_value(values, header_map, "product_key")),
                "departure": clean_text(get_row_value(values, header_map, "departure")),
                "arrival": clean_text(get_row_value(values, header_map, "arrival")),
                "base_analog": clean_decimal(get_row_value(values, header_map, "base_analog")),
                "base_exclusive": clean_decimal(get_row_value(values, header_map, "base_exclusive")),
                "minimum_margin": clean_decimal(get_row_value(values, header_map, "minimum_margin")),
                "distr": clean_decimal(get_row_value(values, header_map, "distr")),
                "distr_1": clean_decimal(get_row_value(values, header_map, "distr_1")),
                "small": clean_decimal(get_row_value(values, header_map, "small")),
                "medium": clean_decimal(get_row_value(values, header_map, "medium")),
                "large": clean_decimal(get_row_value(values, header_map, "large")),
                "row_index": row_index,
            })
        if not rows:
            raise ValueError("Excel не содержит строк конфигурации")

        product_keys = {row["product_key"] for row in rows if row["product_key"]}
        context = build_validation_context(product_keys)
        configs = {}
        for row in rows:
            validate_row(row, context)
            key = (
                row["product_key"],
                normalize_key(row["departure"]),
                normalize_key(row["arrival"]),
            )
            if key in configs:
                raise ValueError(
                    "В Excel повторяется комбинация product_key + departure + arrival "
                    f"(строки {configs[key]['row_index']} и {row['row_index']})"
                )
            configs[key] = row

        active_base_keys = set(
            ParserProductClassification.objects.filter(
                status=ParserProductClassification.STATUS_ACTIVE,
                product_key__in=ParserProductUrl.objects.filter(
                    status=ParserProductUrl.STATUS_ACTIVE,
                    source="base",
                ).values_list("id", flat=True),
            ).values_list("product_key", flat=True)
        )
        expected_departures = {
            (product_key, departure_key): departure
            for product_key in active_base_keys
            for code in [context["code_by_product"].get(product_key)]
            if code is not None
            for (cost_code, departure_key), departure in context["costs"].items()
            if cost_code == code
        }
        missing = []
        for (product_key, departure_key), departure in expected_departures.items():
            for arrival_key, arrival in context["arrivals"].items():
                if (product_key, departure_key, arrival_key) not in configs:
                    missing.append(
                        f"{product_key}:{departure}->{arrival}"
                    )
        if missing:
            preview = ", ".join(missing[:10])
            suffix = "" if len(missing) <= 10 else f"; ещё {len(missing) - 10}"
            raise ValueError(
                "В Excel отсутствуют обязательные конфигурации: "
                f"{preview}{suffix}"
            )
        return configs
    finally:
        workbook.close()


def config_values_equal(config, row):
    return all(
        Decimal(getattr(config, field_name)) == row[field_name]
        for field_name in ("base_analog", "base_exclusive", "minimum_margin")
    )


def discount_values_equal(discount, row):
    return all(
        Decimal(getattr(discount, field_name)) == row[field_name]
        for field_name in (
            "distr",
            "distr_1",
            "small",
            "medium",
            "large",
        )
    )


def load_iprice_calculation_config_from_xlsx(file_obj) -> dict:
    configs = read_config_rows_from_xlsx(file_obj)
    created = []
    unchanged = []
    deactivated = 0
    discounts_created = []
    discounts_unchanged = []
    discounts_deactivated = 0

    with transaction.atomic():
        active_rows = list(
            IPriceCalculationConfig.objects.select_for_update().filter(is_active=True)
        )
        active_discounts = list(
            DepartureDiscount.objects.select_for_update().filter(
                is_active=True,
            )
        )
        active_by_key = {
            (
                row.product_key,
                normalize_key(row.departure),
                normalize_key(row.arrival),
            ): row
            for row in active_rows
        }
        deactivate_ids = []
        create_rows = []
        active_discounts_by_key = {
            (
                row.product_key,
                normalize_key(row.departure),
                normalize_key(row.arrival),
            ): row
            for row in active_discounts
        }
        discount_deactivate_ids = []
        discount_create_rows = []

        for key, config in configs.items():
            current = active_by_key.get(key)
            if current is not None and config_values_equal(current, config):
                unchanged.append(current)
                continue
            if current is not None:
                deactivate_ids.append(current.id)
            create_rows.append(IPriceCalculationConfig(
                product_key=config["product_key"],
                departure=config["departure"],
                arrival=config["arrival"],
                base_analog=config["base_analog"],
                base_exclusive=config["base_exclusive"],
                minimum_margin=config["minimum_margin"],
                is_active=True,
            ))
            current_discount = active_discounts_by_key.get(key)
            if (
                current_discount is not None
                and discount_values_equal(current_discount, config)
            ):
                discounts_unchanged.append(current_discount)
            else:
                if current_discount is not None:
                    discount_deactivate_ids.append(current_discount.id)
                discount_create_rows.append(DepartureDiscount(
                    product_key=config["product_key"],
                    departure=config["departure"],
                    arrival=config["arrival"],
                    distr=config["distr"],
                    distr_1=config["distr_1"],
                    small=config["small"],
                    medium=config["medium"],
                    large=config["large"],
                    is_active=True,
                ))

        # A config may be unchanged while its discounts changed.
        processed_discount_keys = {
            (
                row.product_key,
                normalize_key(row.departure),
                normalize_key(row.arrival),
            )
            for row in discounts_unchanged
        } | {
            (
                row.product_key,
                normalize_key(row.departure),
                normalize_key(row.arrival),
            )
            for row in discount_create_rows
        }
        for key, config in configs.items():
            if key in processed_discount_keys:
                continue
            current_discount = active_discounts_by_key.get(key)
            if (
                current_discount is not None
                and discount_values_equal(current_discount, config)
            ):
                discounts_unchanged.append(current_discount)
                continue
            if current_discount is not None:
                discount_deactivate_ids.append(current_discount.id)
            discount_create_rows.append(DepartureDiscount(
                product_key=config["product_key"],
                departure=config["departure"],
                arrival=config["arrival"],
                distr=config["distr"],
                distr_1=config["distr_1"],
                small=config["small"],
                medium=config["medium"],
                large=config["large"],
                is_active=True,
            ))

        uploaded_keys = set(configs)
        deactivate_ids.extend(
            row.id for key, row in active_by_key.items()
            if key not in uploaded_keys
        )
        discount_deactivate_ids.extend(
            row.id for key, row in active_discounts_by_key.items()
            if key not in uploaded_keys
        )
        deactivate_ids = sorted(set(deactivate_ids))
        if deactivate_ids:
            deactivated = IPriceCalculationConfig.objects.filter(
                id__in=deactivate_ids,
                is_active=True,
            ).update(is_active=False)
        if create_rows:
            created = IPriceCalculationConfig.objects.bulk_create(
                create_rows,
                batch_size=1000,
            )
        discount_deactivate_ids = sorted(set(discount_deactivate_ids))
        if discount_deactivate_ids:
            discounts_deactivated = DepartureDiscount.objects.filter(
                id__in=discount_deactivate_ids,
                is_active=True,
            ).update(is_active=False)
        if discount_create_rows:
            discounts_created = DepartureDiscount.objects.bulk_create(
                discount_create_rows,
                batch_size=1000,
            )

    result = {
        "created": len(created),
        "unchanged": len(unchanged),
        "deactivated": deactivated,
        "active": len(configs),
        "discounts_created": len(discounts_created),
        "discounts_unchanged": len(discounts_unchanged),
        "discounts_deactivated": discounts_deactivated,
    }
    logger.info("iPrice calculation configs loaded: %s", result)
    return result
