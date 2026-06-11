import csv
from datetime import datetime

from datasets.models import FbProject


DATE_FIELDS = {
    "start_date",
    "end_date",
    "subtask_start_date",
    "subtask_end_date",
    "actual_start_project",
    "actual_end_project",
    "actual_start_subtask",
    "actual_end_subtask",
}


SKIP_FIELDS = {
    "id",
    "date_add",
}


def parse_date_value(value):
    if value in (None, "", "-", "NULL", "0000-00-00", "0001-01-01"):
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_int_value(value):
    if value in (None, "", "-", "NULL"):
        return None

    try:
        return int(value)
    except ValueError:
        return None


def clean_row(row: dict) -> dict:
    cleaned = {}

    model_fields = {
        field.name
        for field in FbProject._meta.fields
    }

    for key, value in row.items():
        if key in SKIP_FIELDS:
            continue

        if key not in model_fields:
            continue

        if value == "NULL":
            value = None

        if key in DATE_FIELDS:
            cleaned[key] = parse_date_value(value)
        elif key == "number":
            cleaned[key] = parse_int_value(value)
        else:
            cleaned[key] = value if value not in ("", "NULL") else None

    return cleaned


def load_fb_project_csv(file_path: str) -> int:
    FbProject.objects.all().delete()

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
            objects.append(FbProject(**cleaned))

    FbProject.objects.bulk_create(
        objects,
        batch_size=1000,
    )

    return len(objects)