import logging

from openpyxl import load_workbook

from datasets.models import ParserPrefix


logger = logging.getLogger("parsers.prefix_loader")


def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def load_parser_prefixes_from_excel(file_obj) -> dict:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    worksheet = workbook.active

    created = 0
    updated = 0
    skipped = 0

    for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        if row_index == 1:
            continue

        source = clean_value(row[0] if len(row) > 0 else None)
        prefix = clean_value(row[1] if len(row) > 1 else None)

        if not source or not prefix:
            skipped += 1
            continue

        obj, is_created = ParserPrefix.objects.update_or_create(
            source=source,
            prefix=prefix,
            defaults={},
        )

        if is_created:
            created += 1
        else:
            updated += 1

    result = {
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }

    logger.info("Parser prefixes loaded from Excel: %s", result)

    return result