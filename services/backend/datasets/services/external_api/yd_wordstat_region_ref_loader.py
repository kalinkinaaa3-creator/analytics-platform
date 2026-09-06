import csv
import logging

from django.db import transaction

from datasets.models import YdWordstatRegionRef
from datasets.services.external_api.yd_wordstat_api_client import (
    fetch_yd_wordstat_regions_tree,
)


logger = logging.getLogger("external_api.yd_wordstat")


CSV_COLUMNS = [
    "country_label",
    "macroregion_label",
    "region_label",
    "region_value",
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

    value = str(value).strip()

    if value == "":
        return None

    try:
        return int(value)
    except Exception:
        return None


def flatten_regions_tree(data):
    """
    Повторяет старую логику:
    1 уровень = страна
    2 уровень = макрорегион
    3 уровень = регион

    В таблицу пишем только регионы.
    Дополнительно добавляем СНГ с region_value=166.
    """

    result = []

    def parse_regions_with_strict_hierarchy(
        nodes,
        current_country=None,
        current_macroregion=None,
    ):
        if not isinstance(nodes, list):
            return

        for node in nodes:
            if not isinstance(node, dict):
                continue

            node_label = clean_str(node.get("label"))
            node_value = clean_int(node.get("value"))
            children = node.get("children") or []

            if current_country is None:
                parse_regions_with_strict_hierarchy(
                    children,
                    current_country={
                        "label": node_label,
                        "value": node_value,
                    },
                    current_macroregion=None,
                )

            elif current_macroregion is None:
                parse_regions_with_strict_hierarchy(
                    children,
                    current_country=current_country,
                    current_macroregion={
                        "label": node_label,
                        "value": node_value,
                    },
                )

            else:
                result.append(
                    {
                        "country_label": current_country["label"],
                        "macroregion_label": current_macroregion["label"],
                        "region_label": node_label,
                        "region_value": node_value,
                    }
                )

    if isinstance(data, dict):
        roots = (
            data.get("regions")
            or data.get("items")
            or data.get("result")
            or data.get("data")
            or []
        )
    elif isinstance(data, list):
        roots = data
    else:
        roots = []

    if isinstance(roots, dict):
        roots = [roots]

    parse_regions_with_strict_hierarchy(roots)

    result.append(
        {
            "country_label": "СНГ (исключая Россию)",
            "macroregion_label": "СНГ (исключая Россию)",
            "region_label": "СНГ (исключая Россию)",
            "region_value": 166,
        }
    )

    return result


def save_region_ref_rows(rows):
    objects = []
    seen = set()
    skipped = 0

    for row in rows:
        region_value = clean_int(row.get("region_value"))

        if region_value is None:
            skipped += 1
            continue

        if region_value in seen:
            skipped += 1
            continue

        seen.add(region_value)

        objects.append(
            YdWordstatRegionRef(
                country_label=clean_str(row.get("country_label")),
                macroregion_label=clean_str(row.get("macroregion_label")),
                region_label=clean_str(row.get("region_label")),
                region_value=region_value,
            )
        )

    with transaction.atomic():
        deleted_count, _ = YdWordstatRegionRef.objects.all().delete()
        YdWordstatRegionRef.objects.bulk_create(objects, batch_size=5000)

    return {
        "received": len(rows),
        "saved": len(objects),
        "deleted": deleted_count,
        "skipped": skipped,
    }


def refresh_yd_wordstat_regions_from_api():
    logger.info("YD Wordstat region ref API refresh started")

    data = fetch_yd_wordstat_regions_tree()
    from django.utils import timezone
    from .yd_wordstat_regions_v2_diagnostic import flatten_regions_tree as flatten_v2

    rows, malformed = flatten_v2(data)
    by_id = {row["id"]: row for row in rows}
    if malformed or not rows or len(by_id) != len(rows):
        raise ValueError("Invalid Wordstat v2 region tree; reference was not changed")
    # Keep the configured set and business hierarchy; a v2 tree can have six levels.
    with transaction.atomic():
        objects = list(YdWordstatRegionRef.objects.select_for_update().all())
        if not objects:
            raise ValueError("Import the configured region reference before refreshing labels")
        missing = [obj.region_value for obj in objects if str(obj.region_value) not in by_id]
        if missing:
            raise ValueError(f"Configured regions missing in Wordstat v2: {missing}")
        now = timezone.now()
        for obj in objects:
            if obj.region_value != 166:
                obj.region_label = by_id[str(obj.region_value)]["label"]
            obj.date_add = now
        YdWordstatRegionRef.objects.bulk_update(objects, ["region_label", "date_add"])
    result = {"received": len(rows), "saved": len(objects), "deleted": 0}

    logger.info("YD Wordstat region ref API refresh finished: %s", result)

    return result


def refresh_yd_wordstat_regions_from_csv(csv_path: str):
    logger.info("YD Wordstat region ref CSV refresh started: %s", csv_path)

    rows = []

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
            rows.append(row)

    result = save_region_ref_rows(rows)

    logger.info("YD Wordstat region ref CSV refresh finished: %s", result)

    return result
