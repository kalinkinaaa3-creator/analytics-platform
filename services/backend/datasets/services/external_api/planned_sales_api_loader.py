import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from datasets.models import DashSales
from datasets.services.external_api.planned_sales_api_client import (
    fetch_planned_sales_api_rows,
)


logger = logging.getLogger("external_api.planned_sales")


def clean_str(value, default="-"):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def clean_nullable_str(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_int(value, default=None):
    if value is None or value == "":
        return default

    try:
        return int(float(str(value).replace(" ", "").replace("\xa0", "")))
    except Exception:
        return default


def clean_decimal(value, default=Decimal("0")):
    if value is None or value == "":
        return default

    value = str(value).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")

    try:
        return Decimal(value)
    except InvalidOperation:
        return default


def clean_date(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    if value[:10] == "0001-01-01":
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def add_leading_zeros(inn):
    if inn is None or inn == "":
        return "-"

    inn = str(inn).strip()

    if len(inn) == 9:
        return inn.zfill(10)

    if len(inn) == 11:
        return inn.zfill(12)

    return inn


def get_dash_sales_load_period(end_date=None):
    end_date = end_date or date.today()

    max_date = DashSales.objects.aggregate(
        max_date=Max("date")
    )["max_date"]

    logger.info("DashSales current max date: %s", max_date)

    if max_date is None:
        start_date = date(2022, 1, 1)
    else:
        if end_date.isoweekday() == 6:
            start_date = max_date - timedelta(days=300)
            logger.info("DashSales Saturday reload period: 300 days")
        else:
            start_date = max_date - timedelta(days=150)
            logger.info("DashSales regular reload period: 150 days")

    return start_date, end_date


def normalize_dash_sales_record(record):
    partner_inn = add_leading_zeros(record.get("partner_inn_"))
    con_inn = add_leading_zeros(record.get("con_inn_"))

    return DashSales(
        criterion=clean_str(record.get("criterion_")),
        date=clean_date(record.get("date_")),

        partner=clean_nullable_str(record.get("partner_")),
        partner_code=clean_int(record.get("partner_code_")),
        partner_inn=clean_nullable_str(partner_inn),

        macrosegment=clean_str(record.get("macrosegment_")),
        segment=clean_str(record.get("segment_")),
        manager=clean_str(record.get("manager_")),

        old_branch=clean_str(record.get("old_branch_")),
        old_branch_group=clean_str(record.get("old_branch_group_")),

        macroregion=clean_str(record.get("macroregion_")),
        region_group=clean_str(record.get("region_group_")),
        region=clean_str(record.get("region_")),

        consignee=clean_str(record.get("consignee_")),

        nom_view=clean_str(record.get("nom_view_")),
        nom_category=clean_str(record.get("nom_category_")),
        nom_group=clean_str(record.get("nom_group_")),
        nom=clean_str(record.get("nom_")),
        nom_code=clean_int(record.get("nom_code_")),

        type_doc=clean_nullable_str(record.get("type_doc_")),

        quantity=clean_decimal(record.get("quantity_")),
        cost=clean_decimal(record.get("cost_")),
        weight_total=clean_decimal(record.get("total_weight_1C")),
        revenue=clean_decimal(record.get("revenue_")),

        con_segment=clean_str(record.get("con_segment_")),
        con_manager=clean_str(record.get("con_manager_")),
        con_branch=clean_str(record.get("con_branch_")),
        con_branch_group=clean_str(record.get("con_branch_group_")),
        con_inn=clean_nullable_str(con_inn),
        con_region=clean_str(record.get("con_region_")),

        nom_hier_code=clean_int(record.get("nom_hier_code"), default=0),
        nom_hier=clean_str(record.get("nom_hier")),

        contract_initiator=clean_str(record.get("contract_initiator")),
        contract_project=clean_str(record.get("contract_project")),
        contract_fullname=clean_str(record.get("contract_fullname")),
        contract_industry=clean_str(record.get("contract_industry")),
    )


def load_dash_sales_from_api(
    start_date=None,
    end_date=None,
):
    logger.info("DashSales API load started")

    if start_date is None or end_date is None:
        start_date, end_date = get_dash_sales_load_period(end_date=end_date)

    if start_date > end_date:
        logger.info(
            "DashSales API load skipped: start_date=%s > end_date=%s",
            start_date,
            end_date,
        )

        return {
            "received": 0,
            "saved": 0,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "skipped": True,
        }

    logger.info(
        "DashSales API load period: start_date=%s, end_date=%s",
        start_date,
        end_date,
    )

    rows = fetch_planned_sales_api_rows(
        start_date=start_date,
        end_date=end_date,
    )

    logger.info("DashSales API rows received: %s", len(rows))

    objects = [
        normalize_dash_sales_record(record)
        for record in rows
    ]

    objects = [
        obj
        for obj in objects
        if obj.date is not None
    ]

    logger.info("DashSales normalize finished: objects=%s", len(objects))

    with transaction.atomic():
        logger.info("DashSales PostgreSQL delete started: date >= %s", start_date)

        deleted_count, _ = DashSales.objects.filter(
            date__gte=start_date,
        ).delete()

        logger.info("DashSales PostgreSQL deleted rows: %s", deleted_count)

        DashSales.objects.bulk_create(objects, batch_size=5000)

        logger.info("DashSales PostgreSQL insert finished: rows=%s", len(objects))

    return {
        "received": len(rows),
        "saved": len(objects),
        "deleted": deleted_count,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "skipped": False,
    }