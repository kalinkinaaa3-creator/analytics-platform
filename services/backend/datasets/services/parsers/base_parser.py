from .queue_execution import standalone
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

YML_URL = "https://iplast.com/bitrix/catalog_export/iPrice-9j9dpp0l4w7lh.xml"
SELECT_MARKET_YML_URL = "https://selectmarket.ru/bitrix/catalog_export/iPrice-8j9dewr42w7lh.xml"


class BaseParserError(Exception):
    pass


def _model(name, workspace):
    if workspace is not None:
        return workspace.model(name)
    return {"BaseProductPrice": BaseProductPrice, "ParserProductProperty": ParserProductProperty,
            "ParserProductUrl": ParserProductUrl}[name]


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


def fetch_yml_root(*, url=None):
    url = url or YML_URL
    logger.info("Base YML request: %s", url)

    response = requests.get(
        url,
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


def parse_offer(offer, *, workspace=None) -> dict | None:
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

    category_tag = offer.find("categoryId")
    category_id = clean_int(category_tag.text if category_tag is not None else None)

    color = None
    code_1c = None
    properties = []

    for param in offer.findall("param"):
        param_name = clean_text(param.get("name"))
        param_value = clean_text(param.text)

        if not param_name or not param_value:
            continue

        param_name_lower = param_name.lower()

        if param_name_lower == "цвет":
            color = param_value
            continue

        if param_name_lower == "код товара":
            code_1c = workspace.product_code(param_value) if workspace is not None and workspace.code == "select-market" else clean_int(param_value)
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


def sync_base_urls(parsed_offers: list[dict], *, workspace=None, deactivate_missing=True) -> dict:
    ParserProductUrl = _model("ParserProductUrl", workspace)
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

        inactivated = (inactive_qs if deactivate_missing else inactive_qs.none()).update(
            status=ParserProductUrl.STATUS_INACTIVE,
            last_error=MISSING_FROM_MAP,
        )

    return {
        "created": created,
        "updated": updated,
        "inactivated": inactivated,
        "active_ids": active_ids,
    }


def save_base_offer_data(item: dict, *, workspace=None) -> dict:
    ParserProductUrl = _model("ParserProductUrl", workspace)
    ParserProductProperty = _model("ParserProductProperty", workspace)
    BaseProductPrice = _model("BaseProductPrice", workspace)
    product_url = item["product_url_obj"]
    product_key = product_url.id
    today = timezone.localdate() if workspace is not None and workspace.code == "select-market" else date.today()
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


def mark_base_offer_failed(product_url: ParserProductUrl, error: Exception, *, workspace=None) -> None:
    ParserProductUrl = _model("ParserProductUrl", workspace)
    ParserProductUrl.objects.filter(id=product_url.id).update(
        is_loaded=False,
        last_error=str(error),
        date_update=timezone.now(),
    )


@standalone("base")
def load_base_products(limit: int | None = None, *, workspace=None) -> dict:
    if workspace is not None and workspace.code == "select-market":
        from django.conf import settings
        root = fetch_yml_root(url=getattr(settings, "SELECT_MARKET_IPRICE_YML_URL", "") or SELECT_MARKET_YML_URL)
        with transaction.atomic():
            from organizations.models import Organization
            Organization.objects.select_for_update().get(code=workspace.code)
            return _load_base_products(root, limit=limit, workspace=workspace)
    return _load_base_products(fetch_yml_root(), limit=limit, workspace=workspace)


def _load_base_products(root, *, limit=None, workspace=None):

    offers = root.findall(".//offer")

    logger.info("Base YML offers found: %s", len(offers))

    parsed_offers = []
    skipped = 0

    for offer in offers:
        item = parse_offer(offer, workspace=workspace)

        if not item:
            skipped += 1
            continue

        parsed_offers.append(item)

    is_select_market = workspace is not None and workspace.code == "select-market"
    if is_select_market:
        if not parsed_offers or skipped or any(not item["code_1c"] for item in parsed_offers):
            raise BaseParserError("YML must contain a complete nonempty catalog with product codes")
        urls = [item["url"] for item in parsed_offers]
        if len(set(urls)) != len(urls):
            raise BaseParserError("YML contains duplicate product URLs")
        if limit is not None and limit <= 0:
            raise BaseParserError("Limit must be positive")
    if limit:
        parsed_offers = parsed_offers[:limit]

    sync_result = sync_base_urls(parsed_offers, workspace=workspace, deactivate_missing=not (is_select_market and limit is not None))

    success = 0
    failed = 0
    inactive = 0
    properties_total = 0
    prices_total = 0

    for item in parsed_offers:
        product_url = item["product_url_obj"]

        try:
            saved = save_base_offer_data(item, workspace=workspace)

            success += 1
            properties_total += saved["properties"]
            prices_total += saved["prices"]

        except Exception as exc:
            if is_select_market:
                raise
            failed += 1
            mark_base_offer_failed(product_url, exc, workspace=workspace)

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

    if is_select_market:
        from select_market.models import Product
        codes = {item["code_1c"] for item in parsed_offers}
        matched = Product.objects.filter(sku__in=codes).count()
        result["matched_sps_codes"] = matched
        result["unmatched_sps_codes"] = len(codes) - matched
    else:
        from sales_calculator.refresh import source_updated
        source_updated()
    return result
