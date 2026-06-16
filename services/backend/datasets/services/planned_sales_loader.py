import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime

from openpyxl import load_workbook

from datasets.models import (
    PlannedSales,
    PlanSales,
    PlannedSalesDirectory,
)


def clean_str(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_level(value):
    value = clean_str(value)

    if value is None:
        return "-"

    return value


def clean_date(value):
    value = clean_str(value)

    if value is None:
        return None

    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d.%m.%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"Invalid date: {value}")




def clean_decimal(value):
    value = clean_str(value)

    if value is None:
        return None

    value = (
        str(value)
        .strip()
        .replace(" ", "")
        .replace("\xa0", "")
        .replace(",", ".")
    )

    if value == "":
        return None

    if value.lower() in ("null", "none", "nan"):
        return None

    if value in ("-", "—"):
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Invalid decimal: {value}")




def clean_int(value):
    value = clean_str(value)

    if value is None:
        return None

    value = value.replace(" ", "").replace("\xa0", "")

    if value == "":
        return None

    return int(float(value))


def load_planned_sales_csv(file_path):
    PlannedSales.objects.all().delete()

    objects = []

    with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                PlannedSales(
                    date=clean_date(row.get("date")),
                    level1=clean_level(row.get("level1")),
                    level2=clean_level(row.get("level2")),
                    level3=clean_level(row.get("level3")),
                    fact=clean_decimal(row.get("fact")),
                    appg=clean_decimal(row.get("appg")),
                    appg_slice=clean_decimal(row.get("appg_slice")),
                    id_directory=clean_int(row.get("id_directory")),
                )
            )

    PlannedSales.objects.bulk_create(objects, batch_size=5000)

    return PlannedSales.objects.count()


def load_plan_sales_csv(file_path):
    PlanSales.objects.all().delete()

    objects = []

    with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                PlanSales(
                    date=clean_date(row.get("date")),
                    level1=clean_level(row.get("level1")),
                    level2=clean_level(row.get("level2")),
                    level3=clean_level(row.get("level3")),
                    plan=clean_decimal(row.get("plan")),
                    projection_s=clean_decimal(row.get("projection_s")),
                    id_directory=clean_int(row.get("id_directory")),
                )
            )

    PlanSales.objects.bulk_create(objects, batch_size=5000)

    return PlanSales.objects.count()


def load_planned_sales_directory_xlsx(file_path):
    PlannedSalesDirectory.objects.all().delete()

    workbook = load_workbook(file_path, data_only=True)
    sheet = workbook.active

    headers = [
        clean_str(cell.value)
        for cell in sheet[1]
    ]

    required_headers = [
        "level1",
        "draft2",
        "level2",
        "draft3",
        "level3",
    ]

    for header in required_headers:
        if header not in headers:
            raise ValueError(f"Missing column in xlsx: {header}")

    header_map = {
        header: index
        for index, header in enumerate(headers)
    }

    objects = []

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue

        objects.append(
            PlannedSalesDirectory(
                level1=clean_level(row[header_map["level1"]]),
                draft2=clean_str(row[header_map["draft2"]]),
                level2=clean_level(row[header_map["level2"]]),
                draft3=clean_str(row[header_map["draft3"]]),
                level3=clean_level(row[header_map["level3"]]),
            )
        )

    PlannedSalesDirectory.objects.bulk_create(objects, batch_size=5000)

    return PlannedSalesDirectory.objects.count()