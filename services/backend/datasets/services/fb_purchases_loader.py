import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime

from datasets.models import FBPurchasesUse, FBPurchasesUseIndicator


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


def load_fb_purchases_use_csv(file_path):
    FBPurchasesUse.objects.all().delete()

    objects = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                FBPurchasesUse(
                    quantity_1C=clean_decimal(row.get("quantity_1C")),
                    revenue_1C=clean_decimal(row.get("revenue_1C")),
                    VAT_1C=clean_decimal(row.get("VAT_1C")),
                    nomenclature_code=clean_str(row.get("nomenclature_code")),
                    date_draft=clean_date(row.get("date_draft")),
                    party_status=clean_str(row.get("party_status")),
                    partner=clean_str(row.get("partner")),
                    nomenclature=clean_str(row.get("nomenclature")),
                )
            )

    FBPurchasesUse.objects.bulk_create(objects, batch_size=1000)

    return len(objects)


def load_fb_purchases_indicator_csv(file_path):
    FBPurchasesUseIndicator.objects.all().delete()

    objects = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            objects.append(
                FBPurchasesUseIndicator(
                    indicator=clean_decimal(row.get("indicator")),
                    date_draft=clean_date(row.get("date_draft")),
                )
            )

    FBPurchasesUseIndicator.objects.bulk_create(objects, batch_size=1000)

    return len(objects)