import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit, parse_qs

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from datasets.models import (
    ParserProductUrl,
    ParserProductProperty,
    TaraProductPrice,
)


logger = logging.getLogger("parsers.tara")

SOURCE = "tara"


class BrowserBlockedError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class BrowserServiceError(Exception):
    pass


class BrowserTransportError(BrowserServiceError):
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


def html_has_product_content(html: str) -> bool:
    lower_html = html.lower()

    return (
        "topic__heading" in lower_html
        or "price_matrix_block" in lower_html
        or "props_block__wrapper" in lower_html
        or "properties-group__item" in lower_html
        or 'itemprop="category"' in lower_html
        or "wholesale-call-quantity" in lower_html
        or "price_wrapper_block" in lower_html
    )


def fetch_html_via_browser(url: str) -> str:
    logger.info("Browser request URL: %s", url)

    from .tara_remote import fetch
    return validate_payload(url, fetch(url))


def validate_payload(url, payload):
    status = payload.get("status")
    html = payload.get("html") or ""
    blocked = bool(payload.get("blocked"))
    error = payload.get("error")

    logger.info(
        "Browser response: status=%s blocked=%s html_len=%s error=%s",
        status,
        blocked,
        len(html),
        error,
    )

    if error:
        raise BrowserTransportError('Browser service could not complete the request')

    if status is not None:
        status = int(status)

    lower_html = html.lower()
    has_product_content = html_has_product_content(html)

    if status == 404:
        raise ProductNotFoundError("HTTP 404: product page not found")

    if status == 429:
        raise BrowserBlockedError('HTTP 429: Windows executor paused')

    if status == 502:
        raise BrowserBlockedError('HTTP 502: blocked by Tara')

    if not has_product_content and (status in (401, 403) or blocked or
            re.search(r"forbidden|доступ к сайту[\s\S]{0,200}запрещен", lower_html)):
        raise BrowserBlockedError(f"Blocked by Tara, status={status}")

    if status == 401 and not has_product_content:
        raise BrowserBlockedError("HTTP 401: blocked by Tara")

    if status == 401 and has_product_content:
        logger.warning(
            "HTTP 401 received, but product content found. Continue parsing: url=%s",
            url,
        )

    if blocked and status != 200 and not has_product_content:
        raise BrowserBlockedError(f"Blocked by Tara, status={status}")

    if blocked and has_product_content:
        logger.warning(
            "Blocked flag received, but product content found. Continue parsing: url=%s",
            url,
        )

    if status and status >= 500:
        raise BrowserServiceError(f"HTTP {status}: server error")

    if (
        "access denied" in lower_html
        or "request blocked" in lower_html
    ) and not has_product_content:
        raise BrowserBlockedError(f"Blocked by content, status={status}")

    if "<body" not in lower_html:
        raise BrowserServiceError("Empty or invalid html")

    if not has_product_content:
        raise BrowserServiceError("Product card content not found; existing data preserved")
    if payload.get('final_url'):
        requested, final = urlsplit(url), urlsplit(payload['final_url'])
        oid = parse_qs(requested.query).get('oid')
        if requested.hostname != final.hostname or (oid and parse_qs(final.query).get('oid') != oid):
            raise BrowserServiceError('Unexpected product/region redirect; existing data preserved')

    return html


def parse_properties(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    result = []

    props_block = soup.select_one(".props_block__wrapper")

    if not props_block:
        return result

    for item in props_block.select(".properties-group__item"):
        name_el = item.select_one(".properties-group__name")
        value_el = item.select_one(".properties-group__value")

        name = clean_text(name_el.get_text(" ", strip=True)) if name_el else None
        value = clean_text(value_el.get_text(" ", strip=True)) if value_el else None

        if not name and not value:
            continue

        result.append(
            {
                "properties": name,
                "value": value,
            }
        )

    return result


def parse_price_rows(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    name = None
    category = None
    color = None
    image = None
    special_quantity = None

    name_el = soup.select_one(".topic__heading h1#pagetitle")

    if name_el:
        name = clean_text(name_el.get_text(" ", strip=True))

    category_el = soup.select_one(".product-info meta[itemprop='category']")

    if category_el:
        category = clean_text(category_el.get("content"))

    color_el = soup.select_one(".cnt_item")

    if color_el:
        title = clean_text(color_el.get("title"))

        if title and "Цвет:" in title:
            color = clean_text(title.replace("Цвет:", ""))
        else:
            color = title

    image_el = soup.select_one("#photo-0 a[href]")

    if image_el:
        href = image_el.get("href")

        if href:
            if href.startswith("/upload"):
                domain = base_url.split("/catalog")[0]
                image = domain + href
            else:
                image = href

    special_el = soup.select_one(".wholesale-call-quantity")

    if special_el:
        special_raw = special_el.get("data-quantity")

        try:
            special_quantity = int(special_raw)
        except (TypeError, ValueError):
            special_quantity = None

    price_items = []

    matrix_blocks = soup.select(".price_matrix_block")

    if matrix_blocks:
        target_blocks = [matrix_blocks[1]] if len(matrix_blocks) >= 2 else [matrix_blocks[0]]

        for matrix in target_blocks:
            for block in matrix.select(".price_wrapper_block"):
                interval_el = block.select_one(".price_interval")
                price_el = block.select_one(".price_value")

                interval = clean_text(interval_el.get_text(" ", strip=True)) if interval_el else None
                price = clean_decimal(price_el.get_text(" ", strip=True)) if price_el else None

                if not interval and price is None:
                    continue

                price_items.append(
                    {
                        "properties_price": interval,
                        "price": price,
                    }
                )

    if not price_items:
        price_items.append(
            {
                "properties_price": "Цена и срок поставки по запросу",
                "price": None,
            }
        )

    rows = []

    for item in price_items:
        price = item["price"]

        value_added_tax = None
        final_price = None

        if price is not None:
            value_added_tax = (
                price * Decimal("22") / Decimal("122")
            ).quantize(Decimal("0.01"))

            final_price = (price - value_added_tax).quantize(Decimal("0.01"))

        rows.append(
            {
                "properties_price": item["properties_price"],
                "price": price,
                "value_added_tax": value_added_tax,
                "final_price": final_price,
                "color": color,
                "image": image,
                "special_quantity": special_quantity,
                "category": category,
                "name": name,
            }
        )

    return rows


def save_product_data(
    product_url: ParserProductUrl,
    properties: list[dict],
    prices: list[dict],
) -> dict:
    product_key = product_url.id
    now = timezone.now()
    today = date.today()

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

    price_objects = [
        TaraProductPrice(
            product_key=product_key,
            url=product_url.url,
            properties_price=item.get("properties_price"),
            price=item.get("price"),
            value_added_tax=item.get("value_added_tax"),
            final_price=item.get("final_price"),
            color=item.get("color"),
            image=item.get("image"),
            special_quantity=item.get("special_quantity"),
            category=item.get("category"),
            name=item.get("name"),
        )
        for item in prices
    ]

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

        TaraProductPrice.objects.filter(
            product_key=product_key,
            date_add__date=today,
        ).delete()

        if price_objects:
            TaraProductPrice.objects.bulk_create(
                price_objects,
                batch_size=500,
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
        "prices": len(price_objects),
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
        "Parsing product_url_id=%s url=%s",
        product_url.id,
        product_url.url,
    )

    html = fetch_html_via_browser(product_url.url)

    properties = parse_properties(html)

    prices = parse_price_rows(
        html=html,
        base_url=product_url.url,
    )

    saved = save_product_data(
        product_url=product_url,
        properties=properties,
        prices=prices,
    )

    return {
        "product_url_id": product_url.id,
        "product_key": product_url.id,
        "properties": saved["properties"],
        "prices": saved["prices"],
    }


def parse_tara_products(
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
            models.Q(is_loaded=False)
            | models.Q(date_update__date__lt=today)
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
            "Tara products parsing started: "
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
                    "Tara product parsed: product_url_id=%s product_key=%s properties=%s prices=%s",
                    result["product_url_id"],
                    result["product_key"],
                    result["properties"],
                    result["prices"],
                )

            except ProductNotFoundError as exc:
                failed += 1
                not_found += 1

                mark_url_not_found(product_url_id, exc)

                logger.warning(
                    "Tara product not found: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

            except BrowserBlockedError as exc:
                failed += 1
                blocked += 1

                mark_url_failed(product_url_id, exc)

                logger.warning(
                    "Tara product blocked: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

            except Exception as exc:
                failed += 1

                mark_url_failed(product_url_id, exc)

                logger.exception(
                    "Tara product parse failed: product_url_id=%s error=%s",
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

    logger.info("Tara products parsing finished: %s", result)

    return result
