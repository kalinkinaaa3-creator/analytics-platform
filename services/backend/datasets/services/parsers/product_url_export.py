from io import BytesIO

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from datasets.models import (
    ParserProductUrl,
    ParserProductClassification,
    ParserProductMatch,
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


def build_product_url_control_excel() -> BytesIO:
    active_urls_qs = ParserProductUrl.objects.filter(
        status=ParserProductUrl.STATUS_ACTIVE,
    )

    classified_product_keys = set(
        ParserProductClassification.objects.values_list(
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

    miss_classification_rows = list(
        active_urls_qs
        .exclude(id__in=classified_product_keys)
        .order_by("source", "id")
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

    workbook = Workbook()

    default_sheet = workbook.active
    workbook.remove(default_sheet)

    write_sheet(
        workbook=workbook,
        sheet_name="miss_product_classification",
        rows=miss_classification_rows,
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