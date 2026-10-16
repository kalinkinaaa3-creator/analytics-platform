import logging

from django.db import transaction
from openpyxl import load_workbook

from datasets.models import ParserPrefix as LegacyParserPrefix


logger = logging.getLogger("parsers.prefix_loader")


def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def load_parser_prefixes_from_excel(file_obj, *, workspace=None) -> dict:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        return _load_workbook(workbook, workspace=workspace)
    finally:
        workbook.close()


def _load_workbook(workbook, *, workspace=None):
    ParserPrefix = workspace.model("ParserPrefix") if workspace is not None else LegacyParserPrefix
    worksheet = workbook.active

    rows_by_key = {}
    errors = []

    for row_index, row in enumerate(
        worksheet.iter_rows(values_only=True),
        start=1,
    ):
        if row_index == 1:
            continue
        if workspace is not None and not any(value is not None and str(value).strip() for value in row):
            continue

        source = clean_value(
            row[0] if len(row) > 0 else None
        )

        prefix = clean_value(
            row[1] if len(row) > 1 else None
        )

        shipp_region = clean_value(
            row[2] if len(row) > 2 else None
        )

        if not source:
            errors.append(
                f"Строка {row_index}: не заполнен source"
            )

        if not prefix:
            errors.append(
                f"Строка {row_index}: не заполнен prefix"
            )

        if not shipp_region:
            errors.append(
                f"Строка {row_index}: не заполнен shipp_region"
            )

        if not source or not prefix or not shipp_region:
            continue

        key = (
            source.lower(),
            prefix.lower(),
        )

        existing = rows_by_key.get(key)

        if existing is not None:
            errors.append(
                f"Строка {row_index}: дубликат source/prefix "
                f"({source}, {prefix}), ранее встречался "
                f"в строке {existing['row_index']}"
            )
            continue

        rows_by_key[key] = {
            "row_index": row_index,
            "source": source,
            "prefix": prefix,
            "shipp_region": shipp_region,
        }

    if not rows_by_key and not errors:
        raise ValueError(
            "Parser prefix Excel contains no data rows. "
            "Existing data will not be deleted."
        )

    if errors:
        raise ValueError(
            "Parser prefix Excel validation failed:\n"
            + "\n".join(errors[:100])
        )

    objects = [
        ParserPrefix(
            source=row["source"],
            prefix=row["prefix"],
            shipp_region=row["shipp_region"],
        )
        for row in rows_by_key.values()
    ]

    with transaction.atomic():
        deleted_count, _ = ParserPrefix.objects.all().delete()

        ParserPrefix.objects.bulk_create(
            objects,
            batch_size=1000,
        )

    result = {
        "received_unique": len(rows_by_key),
        "saved": len(objects),
        "deleted": deleted_count,
    }

    logger.info(
        "Parser prefixes loaded from Excel: %s",
        result,
    )

    return result