import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime

from datasets.models import TurnoverClear, TurnoverIndicator


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


def clean_int(value):
    value = clean_str(value)

    if value is None:
        return None

    value = value.replace(" ", "").replace(",", ".")

    try:
        return int(float(value))
    except ValueError:
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


def load_fb_turnover_csv(file_path):
    TurnoverClear.objects.all().delete()

    objects = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                TurnoverClear(
                    date_stock=clean_date(row.get("date_stock")),
                    date_start=clean_date(row.get("date_start")),
                    date_end=clean_date(row.get("date_end")),
                    warehouse_group=clean_str(row.get("warehouse_group")),
                    warehouse=clean_str(row.get("warehouse")),
                    nomenclature=clean_str(row.get("nomenclature")),
                    quantity=clean_str(row.get("quantity")),
                    price=clean_decimal(row.get("price")),
                    amount_day=clean_int(row.get("amount_day")),
                    middle_stock=clean_decimal(row.get("middle_stock")),
                    middle_rubstock=clean_decimal(row.get("middle_rubstock")),
                )
            )

            if len(objects) >= 5000:
                TurnoverClear.objects.bulk_create(objects, batch_size=5000)
                objects = []

    if objects:
        TurnoverClear.objects.bulk_create(objects, batch_size=5000)

    return TurnoverClear.objects.count()


def load_fb_turnover_indicator_csv(file_path):
    TurnoverIndicator.objects.all().delete()

    objects = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                TurnoverIndicator(
                    indicator=clean_int(row.get("indicator")),
                    date_start=clean_date(row.get("date_start")),
                )
            )

    TurnoverIndicator.objects.bulk_create(objects, batch_size=1000)

    return len(objects)