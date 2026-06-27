import csv
import logging
from datetime import datetime

from django.db import transaction

from datasets.models import YdWordstatDeviceRaw


logger = logging.getLogger("external_api.yd_wordstat")


CSV_COLUMNS = [
    "phrase",
    "device",
    "date",
    "count",
    "feature",
    "category",
]


def clean_str(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_int(value):
    if value is None:
        return None

    value = str(value).strip().replace(" ", "").replace("\xa0", "")

    if value == "":
        return None

    try:
        return int(value)
    except Exception:
        return None


def clean_date(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    return None


def load_yd_wordstat_device_raw_from_csv(
    csv_path: str,
    truncate_source: bool = True,
):
    logger.info("YD Wordstat device raw CSV load started: %s", csv_path)

    objects = []
    received = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=",")

        missing_columns = [
            column
            for column in CSV_COLUMNS
            if column not in (reader.fieldnames or [])
        ]

        if missing_columns:
            raise ValueError(
                f"CSV missing columns: {', '.join(missing_columns)}"
            )

        for row in reader:
            received += 1

            phrase = clean_str(row.get("phrase"))
            device = clean_str(row.get("device"))
            row_date = clean_date(row.get("date"))

            if not phrase or not device or row_date is None:
                skipped += 1
                continue

            objects.append(
                YdWordstatDeviceRaw(
                    phrase=phrase,
                    device=device,
                    date=row_date,
                    count=clean_int(row.get("count")) or 0,
                    feature=clean_str(row.get("feature")),
                    category=clean_str(row.get("category")),
                )
            )

    deleted_count = 0

    with transaction.atomic():
        if truncate_source:
            deleted_count, _ = YdWordstatDeviceRaw.objects.all().delete()

        YdWordstatDeviceRaw.objects.bulk_create(objects, batch_size=5000)

    result = {
        "received": received,
        "saved": len(objects),
        "deleted": deleted_count,
        "skipped": skipped,
        "csv_path": csv_path,
        "truncate_source": truncate_source,
    }

    logger.info("YD Wordstat device raw CSV load finished: %s", result)

    return result