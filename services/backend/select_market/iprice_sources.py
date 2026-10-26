"""Upload adapter: shared algorithms, organization-local models and original files."""
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, BadZipFile

from django.core.exceptions import ValidationError
from django.db import transaction
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from xml.etree.ElementTree import ParseError

from organizations.models import Organization
from datasets.services.iprice_workspace import workspace_for
from datasets.services.iprice_upload_template_export import UPLOAD_TEMPLATE_HEADERS
from datasets.services.iprice_calculation_config_loader import clean_decimal
from datasets.services.parsers.prefix_loader import load_parser_prefixes_from_excel
from .iprice_models import IPriceSourceImport
from .iprice_purchase_import import HEADERS as PURCHASE_HEADERS, parse_purchase, load_purchase
from .iprice_regional_import import HEADERS as PARAMETER_HEADERS, parse_parameters, load_parameters

from datasets.services.parsers.product_classification_match_loader import load_product_classification_matches

LOADERS = {
    "product_classification": load_product_classification_matches,
    "product_cost": load_purchase,
    "calculation_config": load_parameters,
    "parser_prefixes": load_parser_prefixes_from_excel,
}


def validate_source(content, kind, workspace):
    if kind not in LOADERS:
        raise ValueError("Неизвестный тип источника.")
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Размер файла не должен превышать 10 МБ.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Распакованный XLSX превышает 100 МБ.")
        book = load_workbook(BytesIO(content), read_only=True, data_only=False)
    except (BadZipFile, OSError, KeyError, InvalidFileException, ParseError) as exc:
        raise ValueError("Не удалось прочитать XLSX.") from exc
    try:
        if len(book.worksheets) != 1:
            raise ValueError("В файле должен быть один лист.")
        rows = book.active.iter_rows(values_only=True)
        expected = PURCHASE_HEADERS if kind == 'product_cost' else PARAMETER_HEADERS if kind == 'calculation_config' else UPLOAD_TEMPLATE_HEADERS[kind]
        header = tuple(str(v).strip() if v is not None else "" for v in next(rows, ()))
        accepted = (tuple(expected), (*expected, 'code_1c', 'name', 'on_website')) if kind == 'product_classification' else (tuple(expected),)
        if header not in accepted:
            raise ValueError("Ожидаются столбцы в порядке шаблона: " + ", ".join(expected))
        if kind == 'product_cost':
            parse_purchase(BytesIO(content))
            return
        if kind == 'calculation_config':
            parse_parameters(BytesIO(content))
            return
        for number, values in enumerate(rows, 2):
            if number > 100001:
                raise ValueError("В файле допускается не более 100 000 строк.")
            if not any(value is not None and str(value).strip() for value in values):
                continue
            row = dict(zip(header, values))
            if any(isinstance(v, str) and v.startswith("=") for v in values):
                raise ValueError(f"Строка {number}: формулы не допускаются, вставьте значения.")
            if kind == "product_classification":
                value = clean_decimal(row.get("product_key"))
                if value is None or not value.is_finite() or value != value.to_integral_value() or not 0 < value < 2**63:
                    raise ValueError(f"Строка {number}: product_key должен быть положительным целым ID товара.")
            if kind == "parser_prefixes" and str(row.get("source", "")).lower() not in {"base", "tara", "ps", "tt"}:
                raise ValueError(f"Строка {number}: неизвестный источник конкурентов.")
            text_model = {"product_classification": "ParserProductClassification", "parser_prefixes": "ParserPrefix"}[kind]
            for field in set(row) & {"source", "prefix", "shipp_region", "category", "subcategory", "subcategory_type", "color", "material", "modification", "article_number_analogs", "item_type"}:
                value = str(row[field]).strip() if row[field] is not None else None
                try:
                    workspace.model(text_model)._meta.get_field(field).clean(value, None)
                except ValidationError as exc:
                    raise ValueError(f"Строка {number}, {field}: {'; '.join(exc.messages)}") from exc
    finally:
        book.close()


def import_source(content, *, kind, filename, user, organization):
    workspace = workspace_for(organization)
    if workspace.code != "select-market":
        raise ValueError("Загрузка доступна только для Селект Маркета.")
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Выберите файл XLSX.")
    validate_source(content, kind, workspace)
    stream = BytesIO(content)
    stream.name = filename
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=organization.pk)
        result = LOADERS[kind](stream, workspace=workspace)
        batch = IPriceSourceImport.objects.create(kind=kind, filename=filename[:255], checksum=sha256(content).hexdigest(),
            content=content, result=result, user=user)
    return {**result, "import_id": batch.pk}
