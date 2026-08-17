import ast
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from datasets.models import (
    ParserProductProperty,
    ParserProductUrl,
    PsProductPrice,
)


logger = logging.getLogger("parsers.ps")

SOURCE = "ps"


class PsBlockedError(Exception):
    pass


class PsNotFoundError(Exception):
    pass


class PsRequestError(Exception):
    pass


def clean_text(value: Any) -> str | None:
    if value is None:
        return None

    value = str(value).replace("\xa0", " ").strip()

    if not value:
        return None

    return re.sub(r"\s+", " ", value)


def clean_decimal(value: Any) -> Decimal | None:
    value = clean_text(value)

    if value is None:
        return None

    value = value.replace(" ", "").replace(",", ".")

    match = re.search(r"\d+(?:\.\d+)?", value)

    if not match:
        return None

    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def calc_vat_and_final_price(price: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    if price is None:
        return None, None

    if price <= 0:
        return Decimal("0.00"), Decimal("0.00")

    vat = (price * Decimal("22") / Decimal("122")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    final_price = (price - vat).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return vat, final_price


def html_has_product_content(html: str) -> bool:
    lower_html = str(html or "").lower()

    return (
        "product-item-detail" in lower_html
        or "product-item-detail-price-current" in lower_html
        or "jccatalogelement" in lower_html
        or "product-item-detail-properties" in lower_html
        or "h1" in lower_html
    )


def is_not_found_content(html: str) -> bool:
    lower_html = str(html or "").lower()

    return (
        "страница в каталоге не найдена" in lower_html
        or "страница не найдена" in lower_html
        or "page not found" in lower_html
        or "not found" in lower_html
    )


def get_base_domain(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def fetch_html(url: str) -> str:
    logger.info("PS product request: %s", url)

    response = requests.get(
        url,
        timeout=60,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/webp,*/*;q=0.8"
            ),
            "Connection": "keep-alive",
        },
        allow_redirects=True,
    )

    status = response.status_code
    html = response.text or ""

    logger.info(
        "PS product response: status=%s html_len=%s url=%s",
        status,
        len(html),
        url,
    )

    has_product_content = html_has_product_content(html)

    if status == 404:
        raise PsNotFoundError("HTTP 404: product page not found")

    if status in (401, 403) and not has_product_content:
        raise PsBlockedError(f"HTTP {status}: blocked by PS server")

    if status >= 500:
        raise PsRequestError(f"HTTP {status}: PS server error")

    lower_html = html.lower()

    if ("access denied" in lower_html or "request blocked" in lower_html) and not has_product_content:
        raise PsBlockedError("Blocked by PS server content")

    if is_not_found_content(html) and not has_product_content:
        raise PsNotFoundError("HTTP 404: product page not found")

    if "<body" not in lower_html:
        raise PsRequestError("Empty or invalid html")

    return html


def parse_offer_data(soup: BeautifulSoup) -> dict:
    color = None
    properties_price = None

    script_data = None

    for script in soup.find_all("script"):
        if script.string and "JCCatalogElement" in script.string:
            script_data = script.string
            break

    if not script_data:
        return {
            "color": color,
            "properties_price": properties_price,
        }

    match = re.search(r"JCCatalogElement\((\{.*?\})\);", script_data, re.S)

    if not match:
        return {
            "color": color,
            "properties_price": properties_price,
        }

    try:
        raw = match.group(1)
        fixed = raw.replace("true", "True").replace("false", "False").replace("null", "None").replace("\\/", "/")

        data = ast.literal_eval(fixed)

        offers = data.get("OFFERS", [])
        tree_props = data.get("TREE_PROPS", [])
        selected_index = int(data.get("OFFER_SELECTED", 0))

        if not offers or selected_index >= len(offers):
            return {
                "color": color,
                "properties_price": properties_price,
            }

        selected_offer = offers[selected_index]
        tree = selected_offer.get("TREE", {})

        for prop in tree_props:
            prop_id = str(prop.get("ID"))
            values = prop.get("VALUES", {})

            value_id = tree.get(f"PROP_{prop_id}")

            if not value_id:
                continue

            value_data = values.get(value_id)

            if not value_data:
                continue

            value_name = clean_text(value_data.get("NAME"))

            if not value_name or value_name == "-":
                continue

            if prop_id == "501":
                color = value_name
            else:
                properties_price = value_name

    except Exception as exc:
        logger.warning("PS offer JS parse failed: %s", exc)

    return {
        "color": color,
        "properties_price": properties_price,
    }


def parse_extra_option_title(soup: BeautifulSoup) -> str | None:
    sku_block = soup.find("div", id=re.compile(r"^bx_.*_sku"))

    if not sku_block:
        return None

    sku_items = sku_block.find_all(
        "div",
        attrs={
            "data-entity": "sku-line-block",
        },
    )

    for item in sku_items:
        title_tag = item.find("div", class_="product-item-scu-container-title")

        if not title_tag:
            continue

        title_text = clean_text(title_tag.get_text(" ", strip=True))

        if not title_text:
            continue

        if title_text.lower() == "цвет":
            continue

        return title_text

    return None


def parse_price_data(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    base_domain = get_base_domain(url)

    name = None
    image = None
    price = None
    discount = 0
    special_quantity = None

    name_tag = soup.select_one("h1.pb-3")

    if name_tag:
        name = clean_text(name_tag.get_text(" ", strip=True))

    img_tag = soup.select_one("div[data-entity='image'] img")

    if img_tag:
        img_path = img_tag.get("data-src") or img_tag.get("src")

        if img_path:
            if img_path.startswith("http"):
                image = img_path
            else:
                image = base_domain + img_path

    price_block = soup.select_one("div.price_list.d-flex.align-items-end")

    if price_block and "display: none" not in price_block.get("style", ""):
        price_tag = price_block.select_one(".product-item-detail-price-current")

        if price_tag:
            price = clean_decimal(price_tag.get_text(" ", strip=True))

    discount_tag = soup.select_one(".product-item-detail-economy-price")

    if discount_tag:
        match = re.search(r"([\d\s]+)", discount_tag.get_text(" ", strip=True))

        if match:
            discount = int(match.group(1).replace(" ", ""))

    label = soup.select_one(".label_status")

    if label:
        match = re.search(r"(\d+)", label.get_text(" ", strip=True))

        if match:
            special_quantity = int(match.group(1))

    offer_data = parse_offer_data(soup)

    color = offer_data["color"]
    properties_price = offer_data["properties_price"]

    extra_option_title = parse_extra_option_title(soup)

    if extra_option_title:
        if properties_price:
            properties_price = f"{properties_price}/{extra_option_title}"
        else:
            properties_price = extra_option_title

    value_added_tax, final_price = calc_vat_and_final_price(price)

    return {
        "price": price,
        "value_added_tax": value_added_tax,
        "final_price": final_price,
        "discount": discount,
        "color": color,
        "image": image,
        "name": name,
        "properties_price": properties_price,
        "special_quantity": special_quantity,
    }


def parse_properties(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    result = []
    seen = set()

    for block in soup.select("ul.product-item-detail-properties"):
        items = block.select("li")

        for item in items:
            name_el = item.select_one(".product-item-detail-properties-name")
            value_el = item.select_one(".product-item-detail-properties-value")

            if not name_el or not value_el:
                continue

            name = clean_text(name_el.get_text(" ", strip=True))
            value = clean_text(value_el.get_text(" ", strip=True))

            if not name or not value:
                continue

            key = (name, value)

            if key in seen:
                continue

            seen.add(key)

            result.append(
                {
                    "properties": name,
                    "value": value,
                }
            )

    if not result:
        result.append(
            {
                "properties": None,
                "value": None,
            }
        )

    return result


def save_product_data(
    product_url: ParserProductUrl,
    price_data: dict,
    properties: list[dict],
) -> dict:
    product_key = product_url.id
    today = date.today()
    now = timezone.now()

    property_objects = [
        ParserProductProperty(
            source=SOURCE,
            product_key=product_key,
            url=product_url.url,
            properties=item.get("properties"),
            value=item.get("value"),
        )
        for item in properties
    ]

    price_object = PsProductPrice(
        product_key=product_key,
        url=product_url.url,
        price=price_data.get("price"),
        value_added_tax=price_data.get("value_added_tax"),
        final_price=price_data.get("final_price"),
        discount=price_data.get("discount"),
        color=price_data.get("color"),
        image=price_data.get("image"),
        name=price_data.get("name"),
        properties_price=price_data.get("properties_price"),
        special_quantity=price_data.get("special_quantity"),
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

        PsProductPrice.objects.filter(
            product_key=product_key,
            date_add__date=today,
        ).delete()

        PsProductPrice.objects.create(
            product_key=price_object.product_key,
            url=price_object.url,
            price=price_object.price,
            value_added_tax=price_object.value_added_tax,
            final_price=price_object.final_price,
            discount=price_object.discount,
            color=price_object.color,
            image=price_object.image,
            name=price_object.name,
            properties_price=price_object.properties_price,
            special_quantity=price_object.special_quantity,
        )

        product_url.is_loaded = True
        product_url.last_error = None
        product_url.date_update = now
        product_url.save(
            update_fields=[
                "is_loaded",
                "last_error",
                "date_update",
            ]
        )

    return {
        "properties": len(property_objects),
        "prices": 1,
    }


def mark_url_failed(product_url_id: int, error: Exception) -> None:
    ParserProductUrl.objects.filter(id=product_url_id).update(
        is_loaded=False,
        last_error=str(error),
        date_update=timezone.now(),
    )


def mark_url_not_found(product_url_id: int, error: Exception) -> None:
    ParserProductUrl.objects.filter(id=product_url_id).update(
        status=ParserProductUrl.STATUS_INACTIVE,
        is_loaded=False,
        last_error=str(error),
        date_update=timezone.now(),
    )


def parse_one_url(product_url_id: int) -> dict:
    product_url = ParserProductUrl.objects.get(id=product_url_id)

    logger.info(
        "PS parsing product_url_id=%s url=%s",
        product_url.id,
        product_url.url,
    )

    html = fetch_html(product_url.url)

    price_data = parse_price_data(
        html=html,
        url=product_url.url,
    )

    properties = parse_properties(html)

    saved = save_product_data(
        product_url=product_url,
        price_data=price_data,
        properties=properties,
    )

    return {
        "product_url_id": product_url.id,
        "product_key": product_url.id,
        "properties": saved["properties"],
        "prices": saved["prices"],
    }


def parse_ps_products(
    limit: int | None = None,
    retry_failed: bool = False,
    blocked_only: bool = False,
    workers: int | None = None,
    product_keys: set[int] | None = None,
) -> dict:
    workers = workers or settings.TARA_PARSER_WORKERS
    today = date.today()

    queryset = ParserProductUrl.objects.filter(
        source=SOURCE,
        status=ParserProductUrl.STATUS_ACTIVE,
    )

    if product_keys is not None:
        queryset = queryset.filter(
            id__in=product_keys,
        )

    if blocked_only:
        queryset = queryset.filter(
            is_loaded=False,
            last_error__icontains="blocked",
        )
    elif retry_failed:
        queryset = queryset.filter(
            is_loaded=False,
            last_error__isnull=False,
        )
    else:
        queryset = queryset.filter(
            models.Q(date_update__date__lt=today)
            | models.Q(date_update__isnull=True)
        )

    product_url_ids = list(
        queryset
        .distinct()
        .order_by("id")
        .values_list("id", flat=True)
    )

    if limit:
        product_url_ids = product_url_ids[:limit]

    if not retry_failed and not blocked_only:
        ParserProductUrl.objects.filter(
            id__in=product_url_ids,
        ).update(
            is_loaded=False,
            last_error=None,
        )

    logger.info(
        (
            "PS products parsing started: "
            "total=%s workers=%s retry_failed=%s "
            "blocked_only=%s product_keys_filter=%s"
        ),
        len(product_url_ids),
        workers,
        retry_failed,
        blocked_only,
        product_keys is not None,
    )

    total = len(product_url_ids)
    success = 0
    failed = 0
    not_found = 0
    blocked = 0
    properties_total = 0
    prices_total = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(parse_one_url, product_url_id): product_url_id
            for product_url_id in product_url_ids
        }

        for future in as_completed(future_map):
            product_url_id = future_map[future]

            try:
                result = future.result()

                success += 1
                properties_total += result["properties"]
                prices_total += result["prices"]

                logger.info(
                    "PS product parsed: product_url_id=%s product_key=%s properties=%s prices=%s",
                    result["product_url_id"],
                    result["product_key"],
                    result["properties"],
                    result["prices"],
                )

            except PsNotFoundError as exc:
                failed += 1
                not_found += 1

                mark_url_not_found(product_url_id, exc)

                logger.warning(
                    "PS product not found: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

            except PsBlockedError as exc:
                failed += 1
                blocked += 1

                mark_url_failed(product_url_id, exc)

                logger.warning(
                    "PS product blocked: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

            except Exception as exc:
                failed += 1

                mark_url_failed(product_url_id, exc)

                logger.exception(
                    "PS product parse failed: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

    result = {
        "total": total,
        "success": success,
        "failed": failed,
        "not_found": not_found,
        "blocked": blocked,
        "properties": properties_total,
        "prices": prices_total,
    }

    logger.info("PS products parsing finished: %s", result)

    return result