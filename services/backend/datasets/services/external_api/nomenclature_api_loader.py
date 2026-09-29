from analytics.services.bitrix_notify import send_bitrix_message
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from datasets.models import Nomenclature
from datasets.services.external_api.nomenclature_api_client import (
    fetch_nomenclature_api_rows,
)


logger = logging.getLogger("external_api.nomenclature")


def clean_str(value, default=None):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def clean_int(value, default=None):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    value = (
        value
        .replace(" ", "")
        .replace("\xa0", "")
        .replace(",", ".")
    )

    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def clean_decimal(value, default=None):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    value = (
        value
        .replace(" ", "")
        .replace("\xa0", "")
        .replace(",", ".")
    )

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return default


def normalize_nomenclature_record(record):
    return Nomenclature(
        nom_code=clean_int(record.get("nom_code"), default=0),

        nom=clean_str(record.get("nom"), default="-"),
        nom_article=clean_str(record.get("nom_article"), default="-"),

        nom_base_unit=clean_str(record.get("nom_base_unit"), default="-"),
        nom_stock_unit=clean_str(record.get("nom_stock_unit"), default="-"),
        nom_report_unit=clean_str(record.get("nom_report_unit"), default="-"),

        nom_cn_fea=clean_str(record.get("nom_cn_fea"), default="-"),
        full_nom=clean_str(record.get("full_nom"), default="-"),

        weight_kg=clean_decimal(record.get("weight_kg"), default=Decimal("0")),
        weight_assembly_kg=clean_decimal(
            record.get("weight_assembly_kg"),
            default=Decimal("0"),
        ),

        nom_view=clean_str(record.get("nom_view"), default="-"),
        nom_group=clean_str(record.get("nom_group"), default="-"),

        nom_hier_code=clean_int(record.get("nom_hier_code"), default=0),
        nom_hier=clean_str(record.get("nom_hier"), default="-"),
        nom_category=clean_str(record.get("nom_category"), default="-"),

        vat=clean_str(record.get("VAT"), default="-"),
        type_rep=clean_str(record.get("type_rep"), default="-"),

        height_mm=clean_str(record.get("height_mm"), default="0"),
        length_mm=clean_str(record.get("length_mm"), default="0"),
        width_mm=clean_str(record.get("width_mm"), default="0"),

        tiering=clean_decimal(record.get("tiering"), default=Decimal("0")),

        color=clean_str(record.get("color"), default="-"),

        quantity_eurotruck=clean_int(
            record.get("quantity_eurotruck"),
            default=0,
        ),
    )


def load_nomenclature_from_api() -> dict:
    try:
        logger.info("Nomenclature API load started")

        rows = fetch_nomenclature_api_rows()

        logger.info(
            "Nomenclature API rows received: %s",
            len(rows),
        )

        if not rows:
            raise ValueError(
                "Nomenclature API returned empty list. Existing data will not be deleted."
            )

        objects = [
            normalize_nomenclature_record(record)
            for record in rows
        ]

        objects = [
            obj
            for obj in objects
            if obj.nom_code
        ]

        logger.info(
            "Nomenclature normalize finished: objects=%s",
            len(objects),
        )

        if not objects:
            raise ValueError(
                "Nomenclature normalize returned 0 valid objects. "
                "Existing data will not be deleted."
            )

        with transaction.atomic():
            logger.info("Nomenclature PostgreSQL delete started")

            deleted_count, _ = Nomenclature.objects.all().delete()

            logger.info(
                "Nomenclature PostgreSQL deleted rows: %s",
                deleted_count,
            )

            Nomenclature.objects.bulk_create(
                objects,
                batch_size=5000,
            )

            logger.info(
                "Nomenclature PostgreSQL insert finished: rows=%s",
                len(objects),
            )

        result = {
            "received": len(rows),
            "saved": len(objects),
            "deleted": deleted_count,
        }

        logger.info(
            "Nomenclature API load finished: %s",
            result,
        )

        from sales_calculator.refresh import source_updated
        source_updated()
        return result
    except Exception:
        logger.exception("Nomenclature API load failed")
        send_bitrix_message("[b]Nomenclature API[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 load_nomenclature_from_api.", logger_name=logger.name)
        raise
