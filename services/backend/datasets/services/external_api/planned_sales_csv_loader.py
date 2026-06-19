import csv
import logging
from datetime import date

from django.db import transaction

from datasets.models import DashSales
from datasets.services.external_api.planned_sales_api_loader import (
    normalize_dash_sales_record,
)


logger = logging.getLogger("external_api.planned_sales")


def load_dash_sales_from_csv(
    csv_path: str,
    start_date: date | None = None,
    truncate: bool = True,
    delimiter: str = ",",
):
    logger.info("DashSales CSV load started: %s", csv_path)

    rows = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)

        for record in reader:
            obj = normalize_dash_sales_record(record)

            if obj.date is None:
                continue

            rows.append(obj)

    logger.info("DashSales CSV normalize finished: objects=%s", len(rows))

    with transaction.atomic():
        if truncate:
            logger.info("DashSales PostgreSQL truncate started")
            deleted_count, _ = DashSales.objects.all().delete()
        elif start_date:
            logger.info("DashSales PostgreSQL delete started: date >= %s", start_date)
            deleted_count, _ = DashSales.objects.filter(date__gte=start_date).delete()
        else:
            deleted_count = 0

        DashSales.objects.bulk_create(rows, batch_size=5000)

    result = {
        "source": "csv",
        "path": csv_path,
        "received": len(rows),
        "saved": len(rows),
        "deleted": deleted_count,
        "truncate": truncate,
    }

    logger.info("DashSales CSV load finished: %s", result)

    return result