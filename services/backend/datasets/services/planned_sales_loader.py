import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime

from openpyxl import load_workbook

from datasets.models import (
    PlannedSales,
    PlanSales,
    PlannedSalesDirectory,
)
from django.db import transaction




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
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value

    value = str(value).strip()

    if value == "":
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




'''
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
'''



def load_plan_sales_xlsx(file_path):
    workbook = load_workbook(file_path, data_only=True)
    sheet = workbook.active

    headers = [
        clean_str(cell.value)
        for cell in sheet[1]
    ]

    required_headers = [
        "date",
        "level1",
        "level2",
        "level3",
        "plan",
        "projection",
        "id_directory",
    ]

    for header in required_headers:
        if header not in headers:
            raise ValueError(
                f"Missing column in xlsx: {header}"
            )

    header_map = {
        header: index
        for index, header in enumerate(headers)
    }

    # id_directory -> строка справочника.
    # level1 / level2 / level3 при загрузке берём только отсюда.
    directory_by_id = {
        item.id: item
        for item in PlannedSalesDirectory.objects.all()
    }

    objects = []
    excel_keys = set()

    for row_number, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2,
    ):
        # Полностью пустые строки пропускаем.
        if not any(value is not None for value in row):
            continue

        row_date = clean_date(
            row[header_map["date"]]
        )

        plan = clean_decimal(
            row[header_map["plan"]]
        )

        projection = clean_decimal(
            row[header_map["projection"]]
        )

        id_directory = clean_int(
            row[header_map["id_directory"]]
        )

        if row_date is None:
            raise ValueError(
                f"Empty date in xlsx row {row_number}"
            )

        if id_directory is None:
            raise ValueError(
                f"Empty id_directory in xlsx row {row_number}"
            )

        directory_item = directory_by_id.get(id_directory)

        if directory_item is None:
            raise ValueError(
                f"Unknown id_directory in xlsx row {row_number}: "
                f"{id_directory}"
            )

        # Значения level1 / level2 / level3 из Excel намеренно
        # не используются. Они остаются в файле только для просмотра.
        level1 = clean_level(directory_item.level1)
        level2 = clean_level(directory_item.level2)
        level3 = clean_level(directory_item.level3)

        # Для одного месяца и одной строки справочника
        # должна быть только одна запись.
        excel_key = (
            row_date,
            id_directory,
        )

        if excel_key in excel_keys:
            raise ValueError(
                f"Duplicate plan row in xlsx row {row_number}: "
                f"date={row_date}, "
                f"id_directory={id_directory}"
            )

        excel_keys.add(excel_key)

        objects.append(
            PlanSales(
                date=row_date,
                level1=level1,
                level2=level2,
                level3=level3,
                plan=plan,
                projection_s=projection,
                id_directory=id_directory,
            )
        )

    if not objects:
        raise ValueError(
            "The xlsx file contains no data rows"
        )

    # Сначала весь Excel проверяется.
    # Старые данные удаляются только после успешной проверки.
    with transaction.atomic():
        PlanSales.objects.all().delete()

        PlanSales.objects.bulk_create(
            objects,
            batch_size=5000,
        )

    return len(objects)




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