import logging
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import requests
from django.db import transaction
from django.utils import timezone

from datasets.models import (
    BaseProductPrice,
    ParserProductProperty,
    ParserProductUrl,
)


logger = logging.getLogger("parsers.base")

SOURCE = "base"
MISSING_FROM_MAP = "missing_from_map"

YML_URL = "https://iplast.com/bitrix/catalog_export/tXGigZ2jLniSF8rAGl2zBvkoWu5stfBIUclzRmUd.php"


class BaseParserError(Exception):
    pass


def clean_text(value: Any) -> str | None:
    if value is None:
        return None

    value = str(value).replace("\xa0", " ").strip()

    if not value:
        return None

    return value


def clean_int(value: Any) -> int | None:
    value = clean_text(value)

    if value is None:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def clean_decimal(value: Any) -> Decimal | None:
    value = clean_text(value)

    if value is None:
        return None

    value = value.replace(" ", "").replace(",", ".")

    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def calc_vat_and_final_price(price: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    if price is None:
        return None, None

    if price <= 0:
        return None, None

    vat = (price * Decimal("22") / Decimal("122")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    final_price = (price - vat).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return vat, final_price


def fetch_yml_root():
    logger.info("Base YML request: %s", YML_URL)

    response = requests.get(
        YML_URL,
        timeout=120,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/xml,text/xml,*/*",
        },
    )
    response.raise_for_status()

    xml_data = response.content

    logger.info(
        "Base YML response: status=%s bytes=%s",
        response.status_code,
        len(xml_data),
    )

    try:
        return ET.fromstring(xml_data)
    except Exception as exc:
        raise BaseParserError(f"XML parsing failed: {exc}") from exc


def parse_offer(offer) -> dict | None:
    offer_id = clean_int(offer.get("id"))

    if not offer_id:
        return None

    url_tag = offer.find("url")
    url = clean_text(url_tag.text if url_tag is not None else None)

    if not url:
        return None

    name_tag = offer.find("name")
    name = clean_text(name_tag.text if name_tag is not None else None)

    price_tag = offer.find("price")
    price = clean_decimal(price_tag.text if price_tag is not None else None)

    picture_tag = offer.find("picture")
    image = clean_text(picture_tag.text if picture_tag is not None else None)

    vendor_tag = offer.find("vendorCode")
    code_1c = clean_int(vendor_tag.text if vendor_tag is not None else None)

    category_tag = offer.find("categoryId")
    category_id = clean_int(category_tag.text if category_tag is not None else None)

    color = None
    properties = []

    for param in offer.findall("param"):
        param_name = clean_text(param.get("name"))
        param_value = clean_text(param.text)

        if not param_name or not param_value:
            continue

        if param_name.lower() == "цвет":
            color = param_value
            continue

        properties.append(
            {
                "properties": param_name,
                "value": param_value,
            }
        )

    if not properties:
        properties.append(
            {
                "properties": None,
                "value": None,
            }
        )

    value_added_tax, final_price = calc_vat_and_final_price(price)

    return {
        "offer_id": offer_id,
        "url": url,
        "status": ParserProductUrl.STATUS_ACTIVE,
        "category_id": category_id,
        "name": name,
        "price": price,
        "value_added_tax": value_added_tax,
        "final_price": final_price,
        "image": image,
        "code_1c": code_1c,
        "color": color,
        "properties": properties,
    }


def sync_base_urls(parsed_offers: list[dict]) -> dict:
    active_ids = set()

    created = 0
    updated = 0
    inactivated = 0

    with transaction.atomic():
        for item in parsed_offers:
            obj, is_created = ParserProductUrl.objects.update_or_create(
                source=SOURCE,
                url=item["url"],
                additional_property=None,
                defaults={
                    "prefix": "-",
                    "status": ParserProductUrl.STATUS_ACTIVE,
                    "last_error": None,
                },
            )

            active_ids.add(obj.id)
            item["product_url_obj"] = obj

            if is_created:
                created += 1
            else:
                updated += 1

        inactive_qs = ParserProductUrl.objects.filter(
            source=SOURCE,
        ).exclude(
            id__in=active_ids,
        )

        inactivated = inactive_qs.update(
            status=ParserProductUrl.STATUS_INACTIVE,
            last_error=MISSING_FROM_MAP,
        )

    return {
        "created": created,
        "updated": updated,
        "inactivated": inactivated,
        "active_ids": active_ids,
    }


def save_base_offer_data(item: dict) -> dict:
    product_url = item["product_url_obj"]
    product_key = product_url.id
    today = date.today()
    now = timezone.now()

    property_objects = [
        ParserProductProperty(
            source=SOURCE,
            product_key=product_key,
            url=item["url"],
            properties=row.get("properties"),
            value=row.get("value"),
        )
        for row in item["properties"]
    ]

    price_object = BaseProductPrice(
        product_key=product_key,
        url=item["url"],
        price=item["price"],
        value_added_tax=item["value_added_tax"],
        final_price=item["final_price"],
        color=item["color"],
        image=item["image"],
        name=item["name"],
        code_1c=item["code_1c"],
    )

    with transaction.atomic():
        ParserProductProperty.objects.filter(
            source=SOURCE,
            product_key=product_key,
        ).delete()

        if property_objects:
            ParserProductProperty.objects.bulk_create(
                property_objects,
                batch_size=500,
            )

        BaseProductPrice.objects.filter(
            product_key=product_key,
            date_add__date=today,
        ).delete()

        BaseProductPrice.objects.create(
            product_key=price_object.product_key,
            url=price_object.url,
            price=price_object.price,
            value_added_tax=price_object.value_added_tax,
            final_price=price_object.final_price,
            color=price_object.color,
            image=price_object.image,
            name=price_object.name,
            code_1c=price_object.code_1c,
        )

        product_url.status = ParserProductUrl.STATUS_ACTIVE
        product_url.is_loaded = True
        product_url.last_error = None
        product_url.date_update = now
        product_url.save(
            update_fields=[
                "status",
                "is_loaded",
                "last_error",
                "date_update",
            ]
        )

    return {
        "properties": len(property_objects),
        "prices": 1,
    }


def mark_base_offer_failed(product_url: ParserProductUrl, error: Exception) -> None:
    ParserProductUrl.objects.filter(id=product_url.id).update(
        is_loaded=False,
        last_error=str(error),
        date_update=timezone.now(),
    )


def load_base_products(limit: int | None = None) -> dict:
    root = fetch_yml_root()

    offers = root.findall(".//offer")

    logger.info("Base YML offers found: %s", len(offers))

    parsed_offers = []
    skipped = 0

    for offer in offers:
        item = parse_offer(offer)

        if not item:
            skipped += 1
            continue

        parsed_offers.append(item)

    if limit:
        parsed_offers = parsed_offers[:limit]

    sync_result = sync_base_urls(parsed_offers)

    success = 0
    failed = 0
    inactive = 0
    properties_total = 0
    prices_total = 0

    for item in parsed_offers:
        product_url = item["product_url_obj"]

        try:
            saved = save_base_offer_data(item)

            success += 1
            properties_total += saved["properties"]
            prices_total += saved["prices"]

        except Exception as exc:
            failed += 1
            mark_base_offer_failed(product_url, exc)

            logger.exception(
                "Base product save failed: product_key=%s url=%s error=%s",
                product_url.id,
                item["url"],
                exc,
            )

    result = {
        "offers": len(offers),
        "parsed": len(parsed_offers),
        "created": sync_result["created"],
        "updated": sync_result["updated"],
        "inactivated": sync_result["inactivated"],
        "success": success,
        "failed": failed,
        "inactive": inactive,
        "skipped": skipped,
        "properties": properties_total,
        "prices": prices_total,
    }

    logger.info("Base products load finished: %s", result)

    return result