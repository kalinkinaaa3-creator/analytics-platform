from collections import defaultdict
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from datasets.models import (
    BaseProductPrice,
    DepartureDiscount,
    Nomenclature,
    ParserProductClassification,
    ParserProductUrl,
)


# ============================================================
# HEADERS
# ============================================================


MAIN_HEADERS = [
    "Код номенклатуры *",
    "Наименование",
    "Вид",
    "Группа",
    "Категория",
    "Регион производства",
]


ERROR_HEADERS = [
    "product_key",
    "code_1c",
    "Регион производства",
    "Ошибка",
]


# ============================================================
# COMMON HELPERS
# ============================================================


def normalize_text(value):
    """
    Приводит текст к нормальному виду.

    None        -> None
    ""          -> None
    "  Азов  "  -> "Азов"
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def _get_local_date(value):
    """
    date_add в Django при USE_TZ=True является timezone-aware.

    Для сравнения записей нас интересует календарный день
    в локальной timezone Django.
    """

    if value is None:
        return None

    if timezone.is_aware(value):
        value = timezone.localtime(value)

    return value.date()


def _autosize_worksheet(worksheet):
    """
    Автоматически подбирает ширину столбцов,
    но ограничивает ее 60 символами.
    """

    for column_cells in worksheet.columns:
        max_length = 0

        for cell in column_cells:
            value = cell.value

            if value is None:
                continue

            max_length = max(
                max_length,
                len(str(value)),
            )

        column_letter = get_column_letter(
            column_cells[0].column
        )

        worksheet.column_dimensions[
            column_letter
        ].width = min(
            max(
                max_length + 2,
                12,
            ),
            60,
        )


# ============================================================
# ACTUAL BASE PRICE ROW
# ============================================================


def _get_latest_base_price_rows(product_keys):
    """
    Для каждого product_key выбирает одну актуальную
    строку BaseProductPrice.

    ЕДИНОЕ ПРАВИЛО iPrice:

    1. Для product_key определяем MAX календарной даты date_add.

    2. Рассматриваем ТОЛЬКО строки этого календарного дня.

    3. Среди строк актуального дня рассматриваем только строки,
       где final_price заполнен.

    4. Выбираем MAX(final_price).

    5. Если строк с одинаковым MAX(final_price) несколько,
       выбираем строку с MIN(id).

    6. Если за актуальный день final_price отсутствует
       во всех строках:
           строку НЕ выбираем;
           product_key попадает в errors.

    Никакого fallback на price нет.

    Возвращает:

        selected_rows = {
            product_key: {
                "id": ...,
                "product_key": ...,
                "code_1c": ...,
                "price": ...,
                "final_price": ...,
                "date_add": ...,
            }
        }

        errors = {
            product_key: "описание ошибки"
        }
    """

    if not product_keys:
        return {}, {}

    rows = list(
        BaseProductPrice.objects.filter(
            product_key__in=product_keys,
        ).values(
            "id",
            "product_key",
            "code_1c",
            "price",
            "final_price",
            "date_add",
        )
    )

    rows_by_product = defaultdict(list)

    for row in rows:
        rows_by_product[
            row["product_key"]
        ].append(row)

    selected_rows = {}
    errors = {}

    for product_key in sorted(product_keys):
        product_rows = rows_by_product.get(
            product_key,
            [],
        )

        # ----------------------------------------------------
        # Вообще нет строк BaseProductPrice
        # ----------------------------------------------------

        if not product_rows:
            errors[product_key] = (
                "Для product_key отсутствуют записи "
                "в base_product_price"
            )
            continue

        # ----------------------------------------------------
        # Оставляем строки с корректным date_add
        # ----------------------------------------------------

        rows_with_date = [
            row
            for row in product_rows
            if row["date_add"] is not None
        ]

        if not rows_with_date:
            errors[product_key] = (
                "Для product_key в base_product_price "
                "не найдено ни одной строки с date_add"
            )
            continue

        # ----------------------------------------------------
        # MAX календарного дня
        # ----------------------------------------------------

        latest_day = max(
            _get_local_date(
                row["date_add"]
            )
            for row in rows_with_date
        )

        # ----------------------------------------------------
        # Только актуальный день
        # ----------------------------------------------------

        latest_rows = [
            row
            for row in rows_with_date
            if (
                _get_local_date(
                    row["date_add"]
                )
                == latest_day
            )
        ]

        # ----------------------------------------------------
        # Только заполненный final_price
        # ----------------------------------------------------

        rows_with_final_price = [
            row
            for row in latest_rows
            if row["final_price"] is not None
        ]

        # ----------------------------------------------------
        # На актуальный день final_price нет
        #
        # ВАЖНО:
        # price НЕ используем вместо final_price.
        # ----------------------------------------------------

        if not rows_with_final_price:
            errors[product_key] = (
                f"За актуальную дату {latest_day} "
                "в base_product_price отсутствует "
                "заполненный final_price"
            )
            continue

        # ----------------------------------------------------
        # MAX(final_price)
        # ----------------------------------------------------

        max_final_price = max(
            row["final_price"]
            for row in rows_with_final_price
        )

        # ----------------------------------------------------
        # Все строки с MAX(final_price)
        # ----------------------------------------------------

        candidates = [
            row
            for row in rows_with_final_price
            if (
                row["final_price"]
                == max_final_price
            )
        ]

        # ----------------------------------------------------
        # Если одинаковая максимальная цена встречается
        # несколько раз — берем меньший id.
        # ----------------------------------------------------

        selected_row = min(
            candidates,
            key=lambda row: row["id"],
        )

        selected_rows[
            product_key
        ] = selected_row

    return selected_rows, errors


# ============================================================
# ECONOMIST EXPORT
# ============================================================


def export_iprice_product_cost_template():
    """
    Формирует предварительную выгрузку для экономиста.

    Пул товаров:

        ParserProductClassification
        status=active
                ↓
        ParserProductUrl
        source=base
        status=active
                ↓
        BaseProductPrice
        product_key
                ↓
        актуальная строка:
        MAX day -> MAX(final_price) -> MIN(id)
                ↓
        code_1c
                ↓
        Nomenclature.nom_code
                ↓
        DepartureDiscount.product_key
                ↓
        departure

    Одна строка основного листа:

        code_1c
        +
        departure

    То есть если товар производится в двух регионах,
    в Excel будет две строки.
    """

    # ========================================================
    # 1. ACTIVE CLASSIFICATION
    # ========================================================

    classification_product_keys = set(
        ParserProductClassification.objects.filter(
            status=(
                ParserProductClassification.STATUS_ACTIVE
            ),
        ).values_list(
            "product_key",
            flat=True,
        )
    )

    # ========================================================
    # 2. ОСТАВЛЯЕМ ТОЛЬКО НАШИ ACTIVE BASE PRODUCT_KEY
    # ========================================================

    base_product_keys = set(
        ParserProductUrl.objects.filter(
            id__in=classification_product_keys,
            source="base",
            status=ParserProductUrl.STATUS_ACTIVE,
        ).values_list(
            "id",
            flat=True,
        )
    )

    errors = []

    if not base_product_keys:
        errors.append({
            "product_key": None,
            "code_1c": None,
            "departure": None,
            "error": (
                "Не найдено активных товаров source=base, "
                "присутствующих в active "
                "parser_product_classification"
            ),
        })

    # ========================================================
    # 3. АКТУАЛЬНАЯ BASEPRODUCTPRICE
    #
    # Для каждого product_key:
    #
    # MAX календарной даты
    #     ↓
    # MAX(final_price)
    #     ↓
    # при одинаковой цене MIN(id)
    #
    # Если final_price нет:
    #     ERROR
    # ========================================================

    (
        latest_base_rows,
        base_price_errors,
    ) = _get_latest_base_price_rows(
        base_product_keys
    )

    # ========================================================
    # 4. PRODUCT_KEY -> CODE_1C
    # ========================================================

    product_code_map = {}

    for product_key in sorted(
        base_product_keys
    ):
        # ----------------------------------------------------
        # Ошибка выбора актуальной BaseProductPrice
        # ----------------------------------------------------

        price_error = (
            base_price_errors.get(
                product_key
            )
        )

        if price_error:
            errors.append({
                "product_key": product_key,
                "code_1c": None,
                "departure": None,
                "error": price_error,
            })
            continue

        price_row = latest_base_rows.get(
            product_key
        )

        if price_row is None:
            errors.append({
                "product_key": product_key,
                "code_1c": None,
                "departure": None,
                "error": (
                    "Не удалось определить актуальную "
                    "строку base_product_price"
                ),
            })
            continue

        code_1c = price_row.get(
            "code_1c"
        )

        if code_1c is None:
            errors.append({
                "product_key": product_key,
                "code_1c": None,
                "departure": None,
                "error": (
                    "В актуальной записи "
                    "base_product_price "
                    "не заполнен code_1c"
                ),
            })
            continue

        product_code_map[
            product_key
        ] = code_1c

    # ========================================================
    # 5. РЕГИОНЫ ПРОИЗВОДСТВА
    #
    # Источник истины:
    #
    # DepartureDiscount
    # product_key + departure + arrival
    #
    # departure = регион производства.
    # ========================================================

    departures_by_product = defaultdict(
        list
    )

    discount_rows = (
        DepartureDiscount.objects
        .filter(
            product_key__in=(
                product_code_map.keys()
            ),
            is_active=True,
        )
        .order_by(
            "product_key",
            "departure",
            "id",
        )
        .values(
            "id",
            "product_key",
            "departure",
        )
    )

    # --------------------------------------------------------
    # В региональной модели одно производство повторяется
    # для разных arrival, поэтому для шаблона себестоимости
    # оставляем уникальные product_key + departure.
    # --------------------------------------------------------

    departure_seen = set()

    for row in discount_rows:
        product_key = row[
            "product_key"
        ]

        departure = normalize_text(
            row["departure"]
        )

        if not departure:
            errors.append({
                "product_key": product_key,
                "code_1c": (
                    product_code_map.get(
                        product_key
                    )
                ),
                "departure": None,
                "error": (
                    "В departure_discount "
                    "не заполнен departure"
                ),
            })
            continue

        normalized_key = (
            product_key,
            departure.casefold(),
        )

        if normalized_key in departure_seen:
            # Технически БД этого допустить не должна,
            # но при отличиях регистра возможна логическая
            # дубликация.
            errors.append({
                "product_key": product_key,
                "code_1c": (
                    product_code_map.get(
                        product_key
                    )
                ),
                "departure": departure,
                "error": (
                    "Обнаружен логический дубликат "
                    "product_key + departure "
                    "в departure_discount"
                ),
            })
            continue

        departure_seen.add(
            normalized_key
        )

        departures_by_product[
            product_key
        ].append(
            departure
        )

    # ========================================================
    # 6. ПРОВЕРЯЕМ, ЧТО ДЛЯ КАЖДОГО BASE PRODUCT
    #    ЕСТЬ ХОТЯ БЫ ОДНО ПРОИЗВОДСТВО
    # ========================================================

    valid_product_keys = []

    for product_key in sorted(
        product_code_map
    ):
        departures = (
            departures_by_product.get(
                product_key,
                [],
            )
        )

        if not departures:
            errors.append({
                "product_key": product_key,
                "code_1c": (
                    product_code_map[
                        product_key
                    ]
                ),
                "departure": None,
                "error": (
                    "Для product_key отсутствуют "
                    "корректные строки "
                    "departure_discount. "
                    "Невозможно определить "
                    "регион производства."
                ),
            })
            continue

        valid_product_keys.append(
            product_key
        )

    # ========================================================
    # 7. ПОЛУЧАЕМ НОМЕНКЛАТУРУ
    # ========================================================

    codes = {
        product_code_map[
            product_key
        ]
        for product_key in valid_product_keys
    }

    nomenclature_rows = list(
        Nomenclature.objects.filter(
            nom_code__in=codes,
        ).values(
            "id",
            "nom_code",
            "nom",
            "nom_view",
            "nom_group",
            "nom_category",
        )
    )

    nomenclature_by_code = defaultdict(
        list
    )

    for row in nomenclature_rows:
        nomenclature_by_code[
            row["nom_code"]
        ].append(row)

    # ========================================================
    # 8. ФОРМИРУЕМ ОСНОВНОЙ НАБОР
    #
    # Логическая гранулярность:
    #
    # product_key
    # +
    # code_1c
    # +
    # departure
    #
    # Но product_key экономисту не выводим.
    # ========================================================

    export_rows = []

    # --------------------------------------------------------
    # Один и тот же code_1c может потенциально встретиться
    # у нескольких product_key.
    #
    # Для экономиста одна комбинация:
    #
    # code_1c + departure
    #
    # должна присутствовать только один раз.
    # --------------------------------------------------------

    exported_keys = set()

    for product_key in sorted(
        valid_product_keys
    ):
        code_1c = product_code_map[
            product_key
        ]

        nom_rows = (
            nomenclature_by_code.get(
                code_1c,
                [],
            )
        )

        # ----------------------------------------------------
        # Код не найден в Nomenclature
        # ----------------------------------------------------

        if not nom_rows:
            for departure in (
                departures_by_product[
                    product_key
                ]
            ):
                errors.append({
                    "product_key": product_key,
                    "code_1c": code_1c,
                    "departure": departure,
                    "error": (
                        f"code_1c={code_1c} "
                        "не найден в "
                        "nomenclature.nom_code"
                    ),
                })

            continue

        # ----------------------------------------------------
        # Один nom_code должен однозначно определять
        # номенклатуру.
        # ----------------------------------------------------

        if len(nom_rows) > 1:
            for departure in (
                departures_by_product[
                    product_key
                ]
            ):
                errors.append({
                    "product_key": product_key,
                    "code_1c": code_1c,
                    "departure": departure,
                    "error": (
                        f"В nomenclature найдено "
                        f"{len(nom_rows)} строк "
                        f"с одинаковым "
                        f"nom_code={code_1c}"
                    ),
                })

            continue

        nom_row = nom_rows[0]

        # ----------------------------------------------------
        # По каждому региону производства отдельная строка
        # ----------------------------------------------------

        for departure in (
            departures_by_product[
                product_key
            ]
        ):
            unique_key = (
                code_1c,
                departure.casefold(),
            )

            if unique_key in exported_keys:
                continue

            exported_keys.add(
                unique_key
            )

            export_rows.append([
                code_1c,
                nom_row["nom"],
                nom_row["nom_view"],
                nom_row["nom_group"],
                nom_row["nom_category"],
                departure,
            ])

    # ========================================================
    # 9. СОРТИРОВКА ОСНОВНОГО ЛИСТА
    #
    # Сначала code_1c,
    # затем регион производства.
    # ========================================================

    export_rows.sort(
        key=lambda row: (
            row[0],
            (
                str(row[5]).casefold()
                if row[5] is not None
                else ""
            ),
        )
    )

    # ========================================================
    # 10. СОЗДАЕМ EXCEL
    # ========================================================

    workbook = Workbook()

    worksheet = workbook.active
    worksheet.title = "Себестоимость"

    worksheet.append(
        MAIN_HEADERS
    )

    for cell in worksheet[1]:
        cell.font = Font(
            bold=True
        )

    for row in export_rows:
        worksheet.append(
            row
        )

    worksheet.freeze_panes = "A2"

    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )

    _autosize_worksheet(
        worksheet
    )

    # ========================================================
    # 11. ЛИСТ ОШИБОК
    # ========================================================

    error_worksheet = (
        workbook.create_sheet(
            title="Ошибки"
        )
    )

    error_worksheet.append(
        ERROR_HEADERS
    )

    for cell in error_worksheet[1]:
        cell.font = Font(
            bold=True
        )

    # --------------------------------------------------------
    # Для удобства сортируем ошибки по product_key/code.
    # --------------------------------------------------------

    errors.sort(
        key=lambda item: (
            (
                item.get("product_key")
                if item.get("product_key")
                is not None
                else -1
            ),
            (
                item.get("code_1c")
                if item.get("code_1c")
                is not None
                else -1
            ),
            (
                str(
                    item.get("departure")
                    or ""
                ).casefold()
            ),
        )
    )

    for error in errors:
        error_worksheet.append([
            error.get(
                "product_key"
            ),
            error.get(
                "code_1c"
            ),
            error.get(
                "departure"
            ),
            error.get(
                "error"
            ),
        ])

    error_worksheet.freeze_panes = (
        "A2"
    )

    error_worksheet.auto_filter.ref = (
        error_worksheet.dimensions
    )

    _autosize_worksheet(
        error_worksheet
    )

    # ========================================================
    # 12. СОХРАНЯЕМ В ПАМЯТЬ
    # ========================================================

    output = BytesIO()

    workbook.save(
        output
    )

    output.seek(0)

    return output
