import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime
from openpyxl import load_workbook
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


def load_fb_purchases_indicator_xlsx(file_path):
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active

    rows_to_create = []
    dates_to_replace = set()

    for row_number, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_number == 1:
            continue

        date_draft = clean_date(row[0] if row else None)
        indicator = clean_decimal(row[1] if row and len(row) > 1 else None)

        if not date_draft:
            continue

        dates_to_replace.add(date_draft)

        rows_to_create.append(
            FBPurchasesUseIndicator(
                date_draft=date_draft,
                indicator=indicator,
            )
        )

    if dates_to_replace:
        FBPurchasesUseIndicator.objects.filter(
            date_draft__in=dates_to_replace
        ).delete()

    FBPurchasesUseIndicator.objects.bulk_create(
        rows_to_create,
        batch_size=1000,
    )

    return {
        "replaced_dates": len(dates_to_replace),
        "created": len(rows_to_create),
    }