import logging

from django.db import transaction
from openpyxl import load_workbook

from datasets.models import (
    YdWordstatPhraseRef,
    YdWordstatDeviceRef,
    YdWordstatIplastRegionRef,
)


logger = logging.getLogger("external_api.yd_wordstat")


def clean_str(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_int(value):
    if value is None or value == "":
        return None

    try:
        return int(value)
    except Exception:
        return None


def read_excel_rows(excel_path: str):
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    sheet = workbook.active

    rows = list(sheet.iter_rows(values_only=True))

    if not rows:
        return [], []

    headers = [
        clean_str(cell)
        for cell in rows[0]
    ]

    data_rows = []

    for row in rows[1:]:
        item = {}

        for index, header in enumerate(headers):
            if not header:
                continue

            item[header] = row[index] if index < len(row) else None

        data_rows.append(item)

    return headers, data_rows


def validate_columns(headers, required_columns):
    missing = [
        column
        for column in required_columns
        if column not in headers
    ]

    if missing:
        raise ValueError(
            f"Excel missing columns: {', '.join(missing)}"
        )


def load_yd_wordstat_phrase_ref_from_excel(excel_path: str):
    logger.info("YD Wordstat phrase ref Excel load started: %s", excel_path)

    headers, rows = read_excel_rows(excel_path)
    validate_columns(headers, ["feature", "category", "phrase"])

    objects = []
    seen_phrases = set()
    skipped = 0

    for row in rows:
        phrase = clean_str(row.get("phrase"))

        if not phrase:
            skipped += 1
            continue

        phrase_key = phrase.lower()

        if phrase_key in seen_phrases:
            skipped += 1
            continue

        seen_phrases.add(phrase_key)

        objects.append(
            YdWordstatPhraseRef(
                feature=clean_str(row.get("feature")),
                category=clean_str(row.get("category")),
                phrase=phrase,
            )
        )

    with transaction.atomic():
        deleted_count, _ = YdWordstatPhraseRef.objects.all().delete()
        YdWordstatPhraseRef.objects.bulk_create(objects, batch_size=5000)

    result = {
        "received": len(rows),
        "saved": len(objects),
        "deleted": deleted_count,
        "skipped": skipped,
    }

    logger.info("YD Wordstat phrase ref Excel load finished: %s", result)

    return result


def load_yd_wordstat_device_ref_from_excel(excel_path: str):
    logger.info("YD Wordstat device ref Excel load started: %s", excel_path)

    headers, rows = read_excel_rows(excel_path)
    validate_columns(headers, ["device"])

    objects = []
    seen_devices = set()
    skipped = 0

    for row in rows:
        device = clean_str(row.get("device"))

        if not device:
            skipped += 1
            continue

        device_key = device.lower()

        if device_key in seen_devices:
            skipped += 1
            continue

        seen_devices.add(device_key)

        objects.append(
            YdWordstatDeviceRef(
                device=device,
            )
        )

    with transaction.atomic():
        deleted_count, _ = YdWordstatDeviceRef.objects.all().delete()
        YdWordstatDeviceRef.objects.bulk_create(objects, batch_size=5000)

    result = {
        "received": len(rows),
        "saved": len(objects),
        "deleted": deleted_count,
        "skipped": skipped,
    }

    logger.info("YD Wordstat device ref Excel load finished: %s", result)

    return result


def load_yd_wordstat_iplast_region_ref_from_excel(excel_path: str):
    logger.info("YD Wordstat Iplast region ref Excel load started: %s", excel_path)

    headers, rows = read_excel_rows(excel_path)
    validate_columns(headers, ["region_value", "macroregion_label"])

    objects = []
    seen_regions = set()
    skipped = 0

    for row in rows:
        region_value = clean_int(row.get("region_value"))
        macroregion_label = clean_str(row.get("macroregion_label"))

        if region_value is None:
            skipped += 1
            continue

        if region_value in seen_regions:
            skipped += 1
            continue

        seen_regions.add(region_value)

        objects.append(
            YdWordstatIplastRegionRef(
                region_value=region_value,
                macroregion_label=macroregion_label,
            )
        )

    with transaction.atomic():
        deleted_count, _ = YdWordstatIplastRegionRef.objects.all().delete()
        YdWordstatIplastRegionRef.objects.bulk_create(objects, batch_size=5000)

    result = {
        "received": len(rows),
        "saved": len(objects),
        "deleted": deleted_count,
        "skipped": skipped,
    }

    logger.info("YD Wordstat Iplast region ref Excel load finished: %s", result)

    return result