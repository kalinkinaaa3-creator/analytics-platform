from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

from datasets.models import (
    ParserProductUrl,
    ParserProductClassification,
    ParserProductMatch,
)

from datasets.services.parsers.product_auto_classification_ml import (
    build_suggested_classification_rows,
)


COLUMNS = [
    "product_key",
    "source",
    "url",
    "lastmod",
    "date_add",
    "date_update",
    "additional_property",
    "is_loaded",
    "last_error",
    "prefix",
    "status",
]

SUGGESTED_CLASSIFICATION_COLUMNS = [
    "product_key",
    "source",
    "url",
    "additional_property",
    "product_name",
    "suggested_category",
    "suggested_subcategory",
    "suggested_subcategory_type",
    "classification_source",
    "confidence",
    "category_confidence",
    "subcategory_confidence",
    "subcategory_type_confidence",
    "status",
    "auto_created_subcategory",
    "suggestion_note",
]

AUTO_CREATED_FILL = PatternFill(
    fill_type="solid",
    fgColor="FFF2CC",
)


def format_value(value):
    if value is None:
        return None

    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    return value


def write_sheet(workbook, sheet_name, rows):
    worksheet = workbook.create_sheet(title=sheet_name)

    worksheet.append(COLUMNS)

    for row in rows:
        worksheet.append([
            format_value(row.get(column))
            for column in COLUMNS
        ])

    for column_index, column_name in enumerate(COLUMNS, start=1):
        worksheet.column_dimensions[get_column_letter(column_index)].width = max(
            15,
            min(len(column_name) + 5, 40),
        )

    worksheet.freeze_panes = "A2"


def write_custom_sheet(workbook, sheet_name, columns, rows):
    worksheet = workbook.create_sheet(title=sheet_name)

    worksheet.append(columns)

    auto_created_column_index = (
        columns.index("auto_created_subcategory") + 1
        if "auto_created_subcategory" in columns
        else None
    )

    for row in rows:
        worksheet.append([
            format_value(row.get(column))
            for column in columns
        ])

        if (
            auto_created_column_index
            and row.get("auto_created_subcategory") is True
        ):
            excel_row_number = worksheet.max_row

            for cell in worksheet[excel_row_number]:
                cell.fill = AUTO_CREATED_FILL

    for column_index, column_name in enumerate(columns, start=1):
        worksheet.column_dimensions[get_column_letter(column_index)].width = max(
            15,
            min(len(column_name) + 5, 45),
        )

    worksheet.freeze_panes = "A2"


def build_product_url_control_excel() -> BytesIO:
    active_urls_qs = ParserProductUrl.objects.filter(
        status=ParserProductUrl.STATUS_ACTIVE,
    )

    classified_product_keys = set(
        ParserProductClassification.objects.filter(
            status=ParserProductClassification.STATUS_ACTIVE,
        ).values_list(
            "product_key",
            flat=True,
        )
    )

    matched_base_product_keys = set(
        ParserProductMatch.objects.values_list(
            "product_key_base",
            flat=True,
        )
    )

    miss_classification_qs = (
        active_urls_qs
        .exclude(id__in=classified_product_keys)
        .order_by("source", "id")
    )

    miss_classification_rows = list(
        miss_classification_qs.values(*[
            "id",
            "source",
            "url",
            "lastmod",
            "date_add",
            "date_update",
            "additional_property",
            "is_loaded",
            "last_error",
            "prefix",
            "status",
        ])
    )

    pass_rows = list(
        active_urls_qs
        .filter(source="base")
        .exclude(id__in=matched_base_product_keys)
        .order_by("id")
        .values(*[
            "id",
            "source",
            "url",
            "lastmod",
            "date_add",
            "date_update",
            "additional_property",
            "is_loaded",
            "last_error",
            "prefix",
            "status",
        ])
    )

    for row in miss_classification_rows:
        row["product_key"] = row.pop("id")

    for row in pass_rows:
        row["product_key"] = row.pop("id")

    suggested_classification_rows = build_suggested_classification_rows(
        product_urls=list(miss_classification_qs),
    )

    workbook = Workbook()

    default_sheet = workbook.active
    workbook.remove(default_sheet)

    write_sheet(
        workbook=workbook,
        sheet_name="miss_product_classification",
        rows=miss_classification_rows,
    )

    write_custom_sheet(
        workbook=workbook,
        sheet_name="suggested_classification",
        columns=SUGGESTED_CLASSIFICATION_COLUMNS,
        rows=suggested_classification_rows,
    )

    write_sheet(
        workbook=workbook,
        sheet_name="pass",
        rows=pass_rows,
    )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    return output