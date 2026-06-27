import csv
import logging
from datetime import datetime

from django.db import transaction

from datasets.models import YdWordstatRegionRaw


logger = logging.getLogger("external_api.yd_wordstat")


CSV_COLUMNS = [
    "phrase",
    "region_label",
    "region_value",
    "date",
    "count",
    "feature",
    "category",
    "country_label",
    "macroregion_label",
    "macroregion_iplast",
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


def load_yd_wordstat_region_raw_from_csv(
    csv_path: str,
    truncate_source: bool = True,
    batch_size: int = 5000,
):
    logger.info("YD Wordstat region raw CSV load started: %s", csv_path)

    received = 0
    saved = 0
    skipped = 0
    deleted_count = 0
    batch = []

    if truncate_source:
        logger.info("YD Wordstat region raw truncate started")
        deleted_count, _ = YdWordstatRegionRaw.objects.all().delete()
        logger.info("YD Wordstat region raw deleted rows: %s", deleted_count)

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
            region_value = clean_int(row.get("region_value"))
            row_date = clean_date(row.get("date"))

            if not phrase or region_value is None or row_date is None:
                skipped += 1
                continue

            batch.append(
                YdWordstatRegionRaw(
                    phrase=phrase,
                    region_label=clean_str(row.get("region_label")),
                    region_value=region_value,
                    date=row_date,
                    count=clean_int(row.get("count")) or 0,
                    feature=clean_str(row.get("feature")),
                    category=clean_str(row.get("category")),
                    country_label=clean_str(row.get("country_label")),
                    macroregion_label=clean_str(row.get("macroregion_label")),
                    macroregion_iplast=clean_str(row.get("macroregion_iplast")),
                )
            )

            if len(batch) >= batch_size:
                with transaction.atomic():
                    YdWordstatRegionRaw.objects.bulk_create(
                        batch,
                        batch_size=batch_size,
                    )

                saved += len(batch)

                logger.info(
                    "YD Wordstat region raw insert progress: saved=%s, received=%s, skipped=%s",
                    saved,
                    received,
                    skipped,
                )

                batch.clear()

        if batch:
            with transaction.atomic():
                YdWordstatRegionRaw.objects.bulk_create(
                    batch,
                    batch_size=batch_size,
                )

            saved += len(batch)
            batch.clear()

    result = {
        "received": received,
        "saved": saved,
        "deleted": deleted_count,
        "skipped": skipped,
        "csv_path": csv_path,
        "truncate_source": truncate_source,
        "batch_size": batch_size,
    }

    logger.info("YD Wordstat region raw CSV load finished: %s", result)

    return result