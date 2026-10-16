from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)


UPLOAD_TEMPLATE_HEADERS = {
    "nomenclature": ("nom_code", "nom", "nom_view", "nom_category", "nom_group", "nom_hier", "quantity_eurotruck"),
    "transport_cost": (
        "departure",
        "arrival",
        "cost",
    ),
    "product_cost": (
        "date",
        "code",
        "name",
        "departure",
        "cost",
    ),
    "calculation_config": (
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
    ),
    "parser_prefixes": (
        "source",
        "prefix",
        "shipp_region",
    ),
    "product_classification": (
        "product_key",
        "category",
        "subcategory",
        "subcategory_type",
        "color",
        "material",
        "modification",
        "article_number_analogs",
        "item_type",
    ),
}


def export_iprice_upload_template(upload_type: str, *, text_codes=False) -> BytesIO:
    headers = UPLOAD_TEMPLATE_HEADERS.get(upload_type)

    if headers is None:
        raise ValueError(
            f"Unknown iPrice upload template: {upload_type}"
        )

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Шаблон загрузки"
    worksheet.append(headers)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    if text_codes and ("code" in headers or "nom_code" in headers):
        column = headers.index("code" if "code" in headers else "nom_code") + 1
        for row in worksheet.iter_rows(min_row=2, max_row=1001, min_col=column, max_col=column):
            row[0].number_format = "@"

    for index, cell in enumerate(worksheet[1], start=1):
        cell.font = Font(bold=True)
        worksheet.column_dimensions[
            get_column_letter(index)
        ].width = max(16, len(str(cell.value)) + 2)

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    output.seek(0)
    return output
