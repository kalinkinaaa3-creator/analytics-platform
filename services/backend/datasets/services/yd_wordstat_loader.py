import csv
from decimal import Decimal, InvalidOperation

from datasets.models import YdWordstatFor


SKIP_FIELDS = {
    "id",
    "date_add",
}


INT_FIELDS = {
    "year",
    "month_1",
    "month_2",
    "month_3",
    "month_4",
    "month_5",
    "month_6",
    "month_7",
    "month_8",
    "month_9",
    "month_10",
    "month_11",
    "month_12",
    "total",
    "desktop",
    "phone",
    "tablet",
    "other_device",
    "ekb_macroregion",
    "kras_macroregion",
    "mos_macroregion",
    "nign_macroregion",
    "novos_macroregion",
    "spb_macroregion",
    "sng_macroregion",
    "other_macroregion",
}


DECIMAL_FIELDS = {
    "average",
    "growth",
    "monthS_1",
    "monthS_2",
    "monthS_3",
    "monthS_4",
    "monthS_5",
    "monthS_6",
    "monthS_7",
    "monthS_8",
    "monthS_9",
    "monthS_10",
    "monthS_11",
    "monthS_12",
}


def clean_empty(value):
    if value in (None, "", "-", "NULL", "null"):
        return None

    return str(value).strip()


def parse_int(value):
    value = clean_empty(value)

    if value is None:
        return None

    try:
        return int(float(value.replace(",", ".")))
    except (ValueError, TypeError):
        return None


def parse_decimal(value):
    value = clean_empty(value)

    if value is None:
        return None

    value = value.replace(",", ".")

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def clean_row(row: dict) -> dict:
    cleaned = {}

    model_fields = {
        field.name
        for field in YdWordstatFor._meta.fields
    }

    for key, value in row.items():
        key = key.strip()

        if key in SKIP_FIELDS:
            continue

        if key not in model_fields:
            continue

        if key in INT_FIELDS:
            cleaned[key] = parse_int(value)

        elif key in DECIMAL_FIELDS:
            cleaned[key] = parse_decimal(value)

        else:
            cleaned[key] = clean_empty(value)

    return cleaned


def load_yd_wordstat_csv(file_path: str) -> int:
    YdWordstatFor.objects.all().delete()

    objects = []

    with open(
        file_path,
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file, delimiter=",")

        for row in reader:
            cleaned = clean_row(row)
            objects.append(YdWordstatFor(**cleaned))

    YdWordstatFor.objects.bulk_create(
        objects,
        batch_size=1000,
    )

    return len(objects)