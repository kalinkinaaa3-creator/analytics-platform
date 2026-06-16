import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime
from openpyxl import load_workbook

from datasets.models import AccreceivUse, AccreceivIndicator


def clean_str(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_decimal(value):
    value = clean_str(value)

    if value is None:
        return None

    value = value.replace(" ", "").replace(",", ".")

    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def clean_date(value):
    value = clean_str(value)

    if value is None:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def load_fb_accreceiv_csv(file_path):
    AccreceivUse.objects.all().delete()

    objects = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                AccreceivUse(
                    date_start=clean_date(row.get("date_start")),
                    date_end=clean_date(row.get("date_end")),
                    partner=clean_str(row.get("partner")),
                    contract_partner=clean_str(row.get("contract_partner")),
                    manager_name=clean_str(row.get("manager_name")),
                    mutual_instock=clean_decimal(row.get("mutual_instock")),
                    mutual_comstock=clean_decimal(row.get("mutual_comstock")),
                    mutual_spenstock=clean_decimal(row.get("mutual_spenstock")),
                    mutual_finstock=clean_decimal(row.get("mutual_finstock")),
                    initial_stock=clean_decimal(row.get("initial_stock")),
                    coming_stock=clean_decimal(row.get("coming_stock")),
                    spending_stock=clean_decimal(row.get("spending_stock")),
                    final_stock=clean_decimal(row.get("final_stock")),
                )
            )

            if len(objects) >= 5000:
                AccreceivUse.objects.bulk_create(objects, batch_size=5000)
                objects = []

    if objects:
        AccreceivUse.objects.bulk_create(objects, batch_size=5000)

    return AccreceivUse.objects.count()




def load_fb_accreceiv_indicator_xlsx(file_path):
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active

    created_count = 0
    skipped_count = 0

    for row_number, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_number == 1:
            continue

        manager_name = clean_str(row[0] if row else None)

        if not manager_name:
            continue

        exists = AccreceivIndicator.objects.filter(
            manager_name=manager_name
        ).exists()

        if exists:
            skipped_count += 1
            continue

        AccreceivIndicator.objects.create(
            manager_name=manager_name
        )

        created_count += 1

    return {
        "created": created_count,
        "skipped": skipped_count,
        "total": created_count + skipped_count,
    }