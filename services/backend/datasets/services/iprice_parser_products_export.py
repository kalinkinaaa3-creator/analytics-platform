from collections import defaultdict
from datetime import datetime
from io import BytesIO

from django.utils import timezone
from django.db.models import Exists, Max, OuterRef

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from datasets.models import (
    BaseProductPrice,
    DepartureDiscount,
    IPriceCalculationConfig,
    Nomenclature,
    ParserProductProperty,
    ParserProductUrl,
    PsProductPrice,
    TaraProductPrice,
    TtProductPrice,
    ParserProductMatch,
    ParserProductClassification,
)


# ============================================================
# CONFIG
# ============================================================


PRICE_MODELS = {
    "base": BaseProductPrice,
    "tara": TaraProductPrice,
    "ps": PsProductPrice,
    "tt": TtProductPrice,
}


URL_EXCLUDED_FIELDS = {
    "id",
}


PRICE_EXCLUDED_FIELDS = {
    "id",
    "date_add",
}


# ============================================================
# EXCEL HELPERS
# ============================================================


def _excel_value(value):
    """
    Приводит значение к формату, поддерживаемому openpyxl.

    Django при USE_TZ=True возвращает timezone-aware datetime.
    Excel timezone не поддерживает.

    Сначала переводим время в локальную timezone Django,
    затем убираем tzinfo.
    """

    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)

        return value.replace(
            tzinfo=None
        )

    return value


def _get_local_date(value):
    """
    Возвращает календарную дату date_add
    в локальной timezone Django.
    """

    if value is None:
        return None

    if timezone.is_aware(value):
        value = timezone.localtime(
            value
        )

    return value.date()


def _model_field_names(
    model,
    excluded=None,
):
    excluded = excluded or set()

    return [
        field.name
        for field in model._meta.fields
        if field.name not in excluded
    ]


def _header_cell(
    worksheet,
    value,
):
    cell = WriteOnlyCell(
        worksheet,
        value=value,
    )

    cell.font = Font(
        bold=True
    )

    return cell


# ============================================================
# CURRENT PRICE ROW
# ============================================================


def _get_latest_price_rows(
    model,
    product_keys,
    *,
    report_missing_final_price=True,
):
    """
    Для каждого product_key выбирает одну актуальную
    строку соответствующей price table.

    ЕДИНОЕ ПРАВИЛО iPrice:

    1. Для product_key определяем MAX календарной даты date_add.

    2. Рассматриваем ТОЛЬКО строки этого календарного дня.

    3. Из строк актуального дня рассматриваем только строки,
       где final_price заполнен.

    4. Выбираем MAX(final_price).

    5. Если несколько строк имеют одинаковый MAX(final_price),
       выбираем строку с MIN(id).

    6. Если за актуальный день final_price отсутствует
       во всех строках:
           для заполнения информационных полей выгрузки
           выбираем строку с MIN(id);
           product_key возвращаем в errors, если
           report_missing_final_price=True.

    7. Если вообще нет price-строк:
           product_key возвращаем в errors.

    ВАЖНО:
    fallback на поле price НЕ используется.

    Возвращает:

        selected_rows = {
            product_key: {
                ...
            }
        }

        errors = {
            product_key: "описание ошибки"
        }
    """

    if not product_keys:
        return {}, {}

    rows = list(
        model.objects.filter(
            product_key__in=product_keys,
        ).values(
            *[
                field.name
                for field in model._meta.fields
            ]
        )
    )

    rows_by_product = defaultdict(
        list
    )

    for row in rows:
        rows_by_product[
            row["product_key"]
        ].append(row)

    selected_rows = {}
    errors = {}

    for product_key in sorted(
        product_keys
    ):
        product_rows = (
            rows_by_product.get(
                product_key,
                [],
            )
        )

        # ----------------------------------------------------
        # Вообще нет price-строк
        # ----------------------------------------------------

        if not product_rows:
            errors[product_key] = (
                "Для product_key отсутствуют записи "
                f"в {model._meta.db_table}"
            )

            continue

        # ----------------------------------------------------
        # Оставляем только строки с date_add
        # ----------------------------------------------------

        rows_with_date = [
            row
            for row in product_rows
            if (
                row.get("date_add")
                is not None
            )
        ]

        if not rows_with_date:
            errors[product_key] = (
                "Для product_key отсутствует date_add "
                f"в {model._meta.db_table}"
            )

            continue

        # ----------------------------------------------------
        # Последний календарный день
        # ----------------------------------------------------

        latest_day = max(
            _get_local_date(
                row["date_add"]
            )
            for row in rows_with_date
        )

        # ----------------------------------------------------
        # Только строки этого дня
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
        # Только строки с final_price
        # ----------------------------------------------------

        rows_with_final_price = [
            row
            for row in latest_rows
            if (
                row.get(
                    "final_price"
                )
                is not None
            )
        ]

        # ----------------------------------------------------
        # Если final_price нет — это ошибка.
        #
        # price как запасной вариант НЕ используется.
        # ----------------------------------------------------

        if not rows_with_final_price:
            if report_missing_final_price:
                errors[product_key] = (
                    f"За актуальную дату {latest_day} "
                    f"в {model._meta.db_table} "
                    "отсутствует заполненный final_price"
                )

            # Price validity and export completeness are separate concerns.
            # A zero/empty price must not become calculation-ready, but the
            # available product metadata (code_1c, name, URL, image, raw
            # price) still has to be visible to the product analyst.
            selected_rows[product_key] = min(
                latest_rows,
                key=lambda row: row["id"],
            )
            continue

        # ----------------------------------------------------
        # MAX(final_price)
        # ----------------------------------------------------

        max_final_price = max(
            row["final_price"]
            for row in (
                rows_with_final_price
            )
        )

        # ----------------------------------------------------
        # Все строки с этой максимальной ценой
        # ----------------------------------------------------

        candidates = [
            row
            for row in (
                rows_with_final_price
            )
            if (
                row["final_price"]
                == max_final_price
            )
        ]

        # ----------------------------------------------------
        # Если одинаковый MAX(final_price) несколько раз,
        # берем минимальный id.
        # ----------------------------------------------------

        selected = min(
            candidates,
            key=lambda row: row["id"],
        )

        selected_rows[
            product_key
        ] = selected

    return (
        selected_rows,
        errors,
    )


# ============================================================
# PROPERTIES PIVOT
# ============================================================


def _get_property_data(
    source,
    product_keys,
):
    """
    Возвращает свойства товаров в pivot-виде.

    Исходная структура:

        product_key
        properties
        value

    Превращается в:

        product_key
        Длина
        Ширина
        Материал
        ...

    Для каждого:

        source
        +
        product_key
        +
        properties

    берем последнюю строку по:

        date_add DESC
        id DESC
    """

    if not product_keys:
        return [], {}

    rows = (
        ParserProductProperty.objects
        .filter(
            source=source,
            product_key__in=(
                product_keys
            ),
        )
        .exclude(
            properties__isnull=True,
        )
        .exclude(
            properties="",
        )
        .order_by(
            "product_key",
            "properties",
            "-date_add",
            "-id",
        )
        .values(
            "id",
            "product_key",
            "properties",
            "value",
        )
    )

    property_values = defaultdict(
        dict
    )

    property_names = set()

    seen = set()

    for row in rows:
        property_name = row[
            "properties"
        ]

        if property_name is None:
            continue

        property_name = str(
            property_name
        ).strip()

        if not property_name:
            continue

        key = (
            row["product_key"],
            property_name,
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        property_names.add(
            property_name
        )

        property_values[
            row["product_key"]
        ][
            property_name
        ] = row["value"]

    return (
        sorted(
            property_names,
            key=lambda value: (
                value.casefold()
            ),
        ),
        property_values,
    )


# ============================================================
# ACTIVE URL POOL
# ============================================================


def _get_active_urls_by_source():
    """
    Получает все ACTIVE parser_product_url
    и группирует по source.

    Classification здесь намеренно не используется,
    потому что продуктовый аналитик получает эту выгрузку
    ДО формирования новой classification.
    """

    result = defaultdict(
        list
    )

    rows = (
        ParserProductUrl.objects
        .filter(
            status=(
                ParserProductUrl.STATUS_ACTIVE
            ),
        )
        .order_by(
            "source",
            "id",
        )
    )

    for obj in rows:
        result[
            obj.source
        ].append(obj)

    return result


# ============================================================
# SOURCE SHEET
# ============================================================


def _add_source_sheet(
    workbook,
    source,
    url_objects,
    price_model,
):
    """
    Формирует один лист:

        base
        tara
        ps
        tt

    Основа:
        структура соответствующей price table

    Затем:
        parser_product_url

    Затем:
        ParserProductProperty pivot

    Последняя колонка:
        price_selection_error

    Даже если price-row определить нельзя,
    ACTIVE product_key остается в выгрузке.
    """

    worksheet = (
        workbook.create_sheet(
            title=source[:31],
        )
    )

    product_keys = [
        obj.id
        for obj in url_objects
    ]

    # --------------------------------------------------------
    # Актуальные цены
    # --------------------------------------------------------

    (
        latest_prices,
        price_errors,
    ) = _get_latest_price_rows(
        price_model,
        product_keys,
        report_missing_final_price=(
            source != "base"
        ),
    )

    # --------------------------------------------------------
    # Свойства
    # --------------------------------------------------------

    (
        property_names,
        property_values,
    ) = _get_property_data(
        source,
        product_keys,
    )

    # --------------------------------------------------------
    # Price fields
    #
    # id и date_add не выгружаем.
    # product_key остается.
    # --------------------------------------------------------

    price_fields = (
        _model_field_names(
            price_model,
            excluded=(
                PRICE_EXCLUDED_FIELDS
            ),
        )
    )

    # --------------------------------------------------------
    # ParserProductUrl fields
    #
    # id не выгружаем повторно,
    # так как он уже представлен как product_key.
    # --------------------------------------------------------

    url_fields = (
        _model_field_names(
            ParserProductUrl,
            excluded=(
                URL_EXCLUDED_FIELDS
            ),
        )
    )

    # --------------------------------------------------------
    # Headers
    # --------------------------------------------------------

    headers = (
        price_fields
        + [
            f"parser_{field_name}"
            for field_name in url_fields
        ]
        + property_names
        + [
            "price_selection_error"
        ]
    )

    worksheet.append([
        _header_cell(
            worksheet,
            header,
        )
        for header in headers
    ])

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    for url_obj in url_objects:
        product_key = (
            url_obj.id
        )

        price_row = (
            latest_prices.get(
                product_key,
                {},
            )
        )

        properties = (
            property_values.get(
                product_key,
                {},
            )
        )

        row = []

        # ----------------------------------------------------
        # Price table structure
        # ----------------------------------------------------

        for field_name in (
            price_fields
        ):
            if (
                field_name
                == "product_key"
            ):
                row.append(
                    product_key
                )

            else:
                row.append(
                    price_row.get(
                        field_name
                    )
                )

        # ----------------------------------------------------
        # ParserProductUrl
        # ----------------------------------------------------

        for field_name in (
            url_fields
        ):
            row.append(
                getattr(
                    url_obj,
                    field_name,
                )
            )

        # ----------------------------------------------------
        # Dynamic property columns
        # ----------------------------------------------------

        for property_name in (
            property_names
        ):
            row.append(
                properties.get(
                    property_name
                )
            )

        # ----------------------------------------------------
        # Ошибка выбора актуальной цены
        # ----------------------------------------------------

        row.append(
            price_errors.get(
                product_key
            )
        )

        # ----------------------------------------------------
        # Excel-safe values
        # ----------------------------------------------------

        worksheet.append([
            _excel_value(value)
            for value in row
        ])


# ============================================================
# BASE -> CODE_1C
# ============================================================


def _get_latest_base_code_rows(
    product_keys,
):
    """
    Для каждого Base product_key получает code_1c
    из той же актуальной price-row.

    Правило выбора строки абсолютно такое же:

        MAX calendar date
        ->
        MAX(final_price)
        ->
        MIN(id)

    Возвращает:

        code_by_product

        price_errors
    """

    (
        latest_rows,
        errors,
    ) = _get_latest_price_rows(
        BaseProductPrice,
        product_keys,
        report_missing_final_price=False,
    )

    result = {}

    for (
        product_key,
        row,
    ) in latest_rows.items():

        result[
            product_key
        ] = row.get(
            "code_1c"
        )

        # ----------------------------------------------------
        # Строка цены выбрана, но code_1c пуст.
        # Это отдельная ошибка.
        # ----------------------------------------------------

        if (
            row.get("code_1c")
            is None
        ):
            errors[
                product_key
            ] = (
                "В актуальной строке "
                "base_product_price "
                "не заполнен code_1c"
            )

    return (
        result,
        errors,
    )


# ============================================================
# IPRICE_BASE SHEET
# ============================================================


def _add_iprice_base_sheet(
    workbook,
    base_url_objects,
):
    """
    Дополнительный лист iPrice_base.

    Здесь берутся ВСЕ ACTIVE source=base product_key
    из ParserProductUrl.

    Classification намеренно НЕ используется:

        полный parser run
            ↓
        эта выгрузка
            ↓
        продуктовый аналитик
            ↓
        classification / match / discount

    На этом листе показываем:

        product_key
        code_1c
        Nomenclature
        DepartureDiscount
        ошибка актуальной Base цены

    Если DepartureDiscount еще не загружен,
    товар все равно отображается одной строкой
    с пустыми полями производства/скидок.
    """

    worksheet = (
        workbook.create_sheet(
            title="iPrice_base",
        )
    )

    product_keys = [
        obj.id
        for obj in (
            base_url_objects
        )
    ]

    # --------------------------------------------------------
    # Current Base row -> code_1c
    # --------------------------------------------------------

    (
        code_by_product,
        base_price_errors,
    ) = _get_latest_base_code_rows(
        product_keys
    )

    # --------------------------------------------------------
    # Nomenclature
    # --------------------------------------------------------

    codes = {
        code
        for code in (
            code_by_product.values()
        )
        if code is not None
    }

    nomenclature_rows = (
        Nomenclature.objects
        .filter(
            nom_code__in=codes,
        )
        .values(
            "id",
            "nom_code",
            "nom",
            "nom_view",
            "nom_group",
            "nom_category",
        )
        .order_by(
            "nom_code",
            "id",
        )
    )

    # --------------------------------------------------------
    # Здесь не блокируем export из-за дублей Nomenclature.
    # Берем первую строку.
    #
    # Preparation-check отдельно выявит дубликат nom_code.
    # --------------------------------------------------------

    nomenclature_by_code = {}

    nomenclature_duplicates = set()

    for row in nomenclature_rows:
        code = row[
            "nom_code"
        ]

        if code in (
            nomenclature_by_code
        ):
            nomenclature_duplicates.add(
                code
            )
            continue

        nomenclature_by_code[
            code
        ] = row

    # --------------------------------------------------------
    # DepartureDiscount
    # --------------------------------------------------------

    discount_rows = (
        DepartureDiscount.objects
        .filter(
            product_key__in=(
                product_keys
            ),
            is_active=True,
        )
        .order_by(
            "product_key",
            "departure",
            "id",
        )
    )

    discounts_by_product = (
        defaultdict(list)
    )

    for discount in (
        discount_rows
    ):
        discounts_by_product[
            discount.product_key
        ].append(
            discount
        )

    # --------------------------------------------------------
    # Headers
    # --------------------------------------------------------

    headers = [
        "product_key",
        "Код номенклатуры",
        "Наименование",
        "Вид",
        "Группа",
        "Категория",
        "Производство",
        "Регион продажи",
        "distr",
        "distr_1",
        "small",
        "medium",
        "large",
        "price_selection_error",
        "nomenclature_error",
    ]

    worksheet.append([
        _header_cell(
            worksheet,
            header,
        )
        for header in headers
    ])

    # --------------------------------------------------------
    # Rows
    # --------------------------------------------------------

    for product_key in sorted(
        product_keys
    ):
        code_1c = (
            code_by_product.get(
                product_key
            )
        )

        nomenclature = (
            nomenclature_by_code.get(
                code_1c,
                {},
            )
        )

        price_error = (
            base_price_errors.get(
                product_key
            )
        )

        # ----------------------------------------------------
        # Nomenclature error
        # ----------------------------------------------------

        nomenclature_error = None

        if (
            code_1c is not None
            and not nomenclature
        ):
            nomenclature_error = (
                f"code_1c={code_1c} "
                "не найден в nomenclature"
            )

        elif (
            code_1c
            in nomenclature_duplicates
        ):
            nomenclature_error = (
                f"Для nom_code={code_1c} "
                "в nomenclature найдено "
                "несколько строк"
            )

        discounts = (
            discounts_by_product.get(
                product_key,
                [],
            )
        )

        # ----------------------------------------------------
        # Если скидки/производства еще не загружены,
        # товар все равно должен попасть в файл.
        # ----------------------------------------------------

        if not discounts:
            row = [
                product_key,
                code_1c,
                nomenclature.get(
                    "nom"
                ),
                nomenclature.get(
                    "nom_view"
                ),
                nomenclature.get(
                    "nom_group"
                ),
                nomenclature.get(
                    "nom_category"
                ),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                price_error,
                nomenclature_error,
            ]

            worksheet.append([
                _excel_value(value)
                for value in row
            ])

            continue

        # ----------------------------------------------------
        # Один товар может иметь несколько производств.
        # Поэтому строки размножаются.
        # ----------------------------------------------------

        for discount in discounts:
            row = [
                product_key,
                code_1c,
                nomenclature.get(
                    "nom"
                ),
                nomenclature.get(
                    "nom_view"
                ),
                nomenclature.get(
                    "nom_group"
                ),
                nomenclature.get(
                    "nom_category"
                ),
                discount.departure,
                discount.arrival,
                discount.distr,
                discount.distr_1,
                discount.small,
                discount.medium,
                discount.large,
                price_error,
                nomenclature_error,
            ]

            worksheet.append([
                _excel_value(value)
                for value in row
            ])


# ============================================================
# ACTIVE PRODUCT CLASSIFICATION SHEET
# ============================================================


def _add_active_product_classification_sheet(
    workbook,
):
    """
    Выгружает действующую классификацию товаров.

    В лист входят только действующие классификации.
    """

    worksheet = workbook.create_sheet(
        title="product_classification",
    )

    headers = [
        "product_key",
        "category",
        "subcategory",
        "subcategory_type",
        "color",
        "material",
        "modification",
        "article_number_analogs",
        "image",
        "url",
        "item_type",
    ]

    worksheet.append([
        _header_cell(
            worksheet,
            header,
        )
        for header in headers
    ])

    classification_rows = list(
        ParserProductClassification.objects
        .filter(
            status=(
                ParserProductClassification
                .STATUS_ACTIVE
            ),
        )
        .order_by(
            "product_key",
        )
        .values(
            "product_key",
            "category",
            "subcategory",
            "subcategory_type",
            "material",
            "color",
            "modification",
            "article_number_analogs",
            "item_type",
            "url",
            "image",
        )
    )

    if not classification_rows:
        return

    for classification in (
        classification_rows
    ):
        row = [
            classification["product_key"],
            classification["category"],
            classification["subcategory"],
            classification[
                "subcategory_type"
            ],
            classification["color"],
            classification["material"],
            classification[
                "modification"
            ],
            classification["article_number_analogs"],
            classification["image"],
            classification["url"],
            classification["item_type"],
        ]

        worksheet.append([
            _excel_value(value)
            for value in row
        ])


# ============================================================
# ACTIVE PRODUCT MATCH SHEET
# ============================================================


def _add_active_product_match_sheet(
    workbook,
):
    """
    Формирует лист product_match.

    Выгружаются только ACTIVE связи.

    Колонки:

        наш product_key;
        URL нашего товара;
        competitor product_key;
        URL конкурента;
        source конкурента;
        prefix конкурента;
        способ добавления;
        технический status.
    """

    worksheet = workbook.create_sheet(
        title="product_match",
    )

    headers = [
        "product_key_base",
        "base_url",
        "product_key_competitor",
        "competitor_url",
        "competitor_source",
        "competitor_prefix",
        "match_type",
        "match_type_name",
        "status",
    ]

    worksheet.append([
        _header_cell(
            worksheet,
            header,
        )
        for header in headers
    ])

    match_rows = list(
        ParserProductMatch.objects
        .filter(
            status=(
                ParserProductMatch
                .STATUS_ACTIVE
            ),
        )
        .order_by(
            "product_key_base",
            "product_key_competitor",
            "id",
        )
        .values(
            "id",
            "product_key_base",
            "product_key_competitor",
            "match_type",
            "status",
        )
    )

    if not match_rows:
        return

    product_keys = {
        row["product_key_base"]
        for row in match_rows
    }

    product_keys.update(
        row["product_key_competitor"]
        for row in match_rows
    )

    url_rows = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=product_keys,
            )
            .values(
                "id",
                "source",
                "prefix",
                "url",
                "status",
            )
        )
    }

    match_type_labels = dict(
        ParserProductMatch
        .MATCH_TYPE_CHOICES
    )

    seen_pairs = set()

    for match in match_rows:
        pair = (
            match["product_key_base"],
            match[
                "product_key_competitor"
            ],
        )

        # Дополнительный контроль:
        # если из-за старых данных в БД оказались
        # одинаковые активные пары, в Excel
        # повторно их не выводим.
        if pair in seen_pairs:
            continue

        seen_pairs.add(pair)

        base_url = url_rows.get(
            match["product_key_base"],
            {},
        )

        competitor_url = url_rows.get(
            match[
                "product_key_competitor"
            ],
            {},
        )

        match_type = match.get(
            "match_type"
        )

        row = [
            match["product_key_base"],
            base_url.get("url"),
            match[
                "product_key_competitor"
            ],
            competitor_url.get("url"),
            competitor_url.get("source"),
            competitor_url.get("prefix"),
            match_type,
            match_type_labels.get(
                match_type,
                match_type,
            ),
            match["status"],
        ]

        worksheet.append([
            _excel_value(value)
            for value in row
        ])


# ============================================================
# ACTIVE PRODUCT CLASSIFICATION STATUS
# ============================================================


def _add_classification_status_sheet(workbook):
    """Выгружает активные URL с состоянием относительно классификации.

    Контрольная точка — последняя загрузка файла классификации. URL, который
    существовал до неё и ни разу не классифицировался, считается сознательно
    оставленным без классификации. URL, добавленный позже, считается новым
    товаром следующего полного прохода парсеров.

    Активно классифицированные товары также включаются в лист с состоянием
    ``Текущая классификация``. История неактивной классификации отдельно не
    выделяется, чтобы не смешивать её с актуальным состоянием товара.
    """
    worksheet = workbook.create_sheet(title="classification_status")
    headers = [
        "classification_status",
        "product_key",
        "source",
        "prefix",
        "url",
        "additional_property",
        "date_add",
        "date_update",
        "is_loaded",
        "last_error",
    ]
    worksheet.append([_header_cell(worksheet, value) for value in headers])

    classification_boundary = ParserProductClassification.objects.aggregate(
        value=Max("date_update"),
    )["value"]
    active_classification = ParserProductClassification.objects.filter(
        product_key=OuterRef("id"),
        status=ParserProductClassification.STATUS_ACTIVE,
    )
    rows = ParserProductUrl.objects.filter(
        status=ParserProductUrl.STATUS_ACTIVE,
    ).annotate(
        has_active_classification=Exists(active_classification),
    ).order_by("source", "id")

    for row in rows.iterator(chunk_size=1000):
        if row.has_active_classification:
            group = "Текущая классификация"
        elif classification_boundary is None:
            group = "Сознательно не классифицирован ранее"
        elif row.date_add and row.date_add > classification_boundary:
            group = "Новый после последней загрузки классификации"
        else:
            group = "Сознательно не классифицирован ранее"
        worksheet.append([
            group,
            row.id,
            row.source,
            row.prefix,
            row.url,
            row.additional_property,
            _excel_value(row.date_add),
            _excel_value(row.date_update),
            row.is_loaded,
            row.last_error,
        ])


# ============================================================
# ACTIVE CALCULATION CONFIG SHEET
# ============================================================


def _add_active_calculation_config_sheet(
    workbook,
):
    """Выгружает активные коэффициенты в формате загрузки."""

    worksheet = workbook.create_sheet(
        title="calculation_config",
    )

    headers = [
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
    ]

    worksheet.append([
        _header_cell(
            worksheet,
            header,
        )
        for header in headers
    ])

    discounts = {
        (
            row.product_key,
            str(row.departure).strip().casefold(),
            str(row.arrival).strip().casefold(),
        ): row
        for row in DepartureDiscount.objects.filter(
            is_active=True,
            arrival__isnull=False,
        )
    }
    rows = (
        IPriceCalculationConfig.objects.filter(is_active=True)
        .order_by(
            "product_key",
            "departure",
            "arrival",
            "id",
        )
    )

    for row in rows.iterator(
        chunk_size=2000,
    ):
        discount = discounts.get((
            row.product_key,
            str(row.departure).strip().casefold(),
            str(row.arrival).strip().casefold(),
        ))
        worksheet.append([
            _excel_value(row.product_key),
            _excel_value(row.departure),
            _excel_value(row.arrival),
            _excel_value(row.base_analog),
            _excel_value(row.base_exclusive),
            _excel_value(row.minimum_margin),
            _excel_value(discount.distr if discount else None),
            _excel_value(discount.distr_1 if discount else None),
            _excel_value(discount.small if discount else None),
            _excel_value(discount.medium if discount else None),
            _excel_value(discount.large if discount else None),
        ])


# ============================================================
# MAIN EXPORT
# ============================================================


def export_iprice_parser_products():
    """
    Формирует Excel для продуктового аналитика.

    Листы:

        base
        tara
        ps
        tt
        calculation_config
        iPrice_base

    Каждый source-лист:

        ACTIVE ParserProductUrl
            +
        актуальная price-row
            +
        ParserProductUrl fields
            +
        ParserProductProperty pivot
            +
        price_selection_error

    Актуальная price-row:

        MAX calendar date(date_add)
            ↓
        MAX(final_price)
            ↓
        при равенстве MIN(id)

    Если final_price на актуальную дату отсутствует:
        товар НЕ удаляется из выгрузки;
        доступные поля актуальной price-row заполняются;
        final_price остается пустым;
        ошибка пишется в price_selection_error.
    """

    workbook = Workbook(
        write_only=True,
    )

    # --------------------------------------------------------
    # Все ACTIVE ParserProductUrl
    # --------------------------------------------------------

    urls_by_source = (
        _get_active_urls_by_source()
    )

    # --------------------------------------------------------
    # Стабильный порядок листов
    # --------------------------------------------------------

    preferred_order = [
        "base",
        "tara",
        "ps",
        "tt",
    ]

    # --------------------------------------------------------
    # Source sheets
    # --------------------------------------------------------

    for source in (
        preferred_order
    ):
        url_objects = (
            urls_by_source.get(
                source
            )
        )

        if not url_objects:
            continue

        price_model = (
            PRICE_MODELS.get(
                source
            )
        )

        if price_model is None:
            continue

        _add_source_sheet(
            workbook=workbook,
            source=source,
            url_objects=(
                url_objects
            ),
            price_model=(
                price_model
            ),
        )


    # --------------------------------------------------------
    # Active calculation configs
    # --------------------------------------------------------

    _add_active_calculation_config_sheet(
        workbook
    )

    # --------------------------------------------------------
    # Дополнительный Base лист
    # --------------------------------------------------------

    base_url_objects = (
        urls_by_source.get(
            "base",
            [],
        )
    )

    _add_iprice_base_sheet(
        workbook,
        base_url_objects,
    )

    _add_active_product_classification_sheet(workbook)
    _add_active_product_match_sheet(workbook)
    _add_classification_status_sheet(workbook)

    # --------------------------------------------------------
    # Сохраняем workbook в память
    # --------------------------------------------------------

    output = BytesIO()

    workbook.save(
        output
    )

    output.seek(0)

    return output
