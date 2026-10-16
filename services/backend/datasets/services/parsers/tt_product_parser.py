from .queue_execution import standalone
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from datasets.models import (
    ParserProductProperty,
    ParserProductUrl,
    TtProductPrice,
)


logger = logging.getLogger("parsers.tt")

SOURCE = "tt"
BASE_URL = "https://toptara.ru"


class TtBlockedError(Exception):
    pass


class TtNotFoundError(Exception):
    pass


class TtRequestError(Exception):
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


def split_additional_property(value: str | None) -> tuple[str | None, str | None]:
    value = clean_text(value)

    if not value:
        return None, None

    parts = [clean_text(part) for part in value.split("/")]
    parts = [part for part in parts if part]

    if len(parts) == 1:
        return parts[0], None

    return parts[0], parts[1]


def join_additional_property(color: str | None, properties_price: str | None) -> str | None:
    color = clean_text(color)
    properties_price = clean_text(properties_price)

    parts = [item for item in [color, properties_price] if item]

    if not parts:
        return None

    return "/".join(parts)


def html_has_product_content(html: str) -> bool:
    lower_html = str(html or "").lower()

    return (
        "product-name" in lower_html
        or "msoptionsprice" in lower_html
        or "product_tabs_xars" in lower_html
        or "data-rid" in lower_html
    )


def is_not_found_content(html: str) -> bool:
    lower_html = str(html or "").lower()

    return (
        "страница не найдена" in lower_html
        or "page not found" in lower_html
        or "not found" in lower_html
    )


def fetch_html(url: str) -> str:
    logger.info("TT product request: %s", url)

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
        "TT product response: status=%s html_len=%s url=%s",
        status,
        len(html),
        url,
    )

    has_product_content = html_has_product_content(html)
    lower_html = html.lower()

    if status == 404:
        raise TtNotFoundError("HTTP 404: product page not found")

    if status in (401, 403) and not has_product_content:
        raise TtBlockedError(f"HTTP {status}: blocked by TT server")

    if status >= 500:
        raise TtRequestError(f"HTTP {status}: TT server error")

    if ("access denied" in lower_html or "request blocked" in lower_html) and not has_product_content:
        raise TtBlockedError("Blocked by TT server content")

    if is_not_found_content(html) and not has_product_content:
        raise TtNotFoundError("HTTP 404: product page not found")

    if "<body" not in lower_html:
        raise TtRequestError("Empty or invalid html")

    return html


def parse_base_product_data(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    name = None
    rid = None

    name_tag = soup.select_one(".product-name h1")

    if name_tag:
        name = clean_text(name_tag.get_text(" ", strip=True))

    rid_tag = soup.find(attrs={"data-rid": True})

    if rid_tag:
        rid = clean_text(rid_tag.get("data-rid"))

    image = None

    gallery = soup.select("#msGallery a[data-rid]")

    for item in gallery:
        href = item.get("href")

        if href:
            image = urljoin(BASE_URL, href)
            break

    if not image:
        slide_img = soup.select_one("#msGallery img")

        if slide_img:
            src = slide_img.get("src")

            if src:
                image = urljoin(BASE_URL, src)

    return {
        "name": name,
        "rid": rid,
        "image": image,
        "soup": soup,
    }


def parse_properties_from_soup(soup: BeautifulSoup) -> list[dict]:
    result = []
    seen = set()

    for row in soup.select("#product_tabs_xars table tr"):
        tds = row.find_all("td")

        if len(tds) != 2:
            continue

        name = clean_text(tds[0].get_text(" ", strip=True).replace(":", ""))
        value = clean_text(tds[1].get_text(" ", strip=True))

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


def fetch_modification_data(
    *,
    session: requests.Session,
    rid: str,
    color: str | None,
    properties_price: str | None,
) -> list[dict]:
    payload = {
        "id": rid,
        "count": 1,
        "action": "modification/get",
        "ctx": "web",
    }

    if color:
        payload["options[size]"] = color

    if properties_price:
        payload["options[ispolnenie]"] = properties_price

    logger.info(
        "TT modification request: rid=%s color=%s properties_price=%s",
        rid,
        color,
        properties_price,
    )

    response = session.post(
        f"{BASE_URL}/assets/components/msoptionsprice/action.php",
        data=payload,
        timeout=60,
    )

    logger.info(
        "TT modification response: status=%s len=%s",
        response.status_code,
        len(response.text or ""),
    )

    response.raise_for_status()

    payload_json = response.json()

    if not isinstance(payload_json, dict) or not payload_json.get("success"):
        return []

    data_block = payload_json.get("data", {})

    if not isinstance(data_block, dict):
        return []

    global_options = data_block.get("options", {})

    if not isinstance(global_options, dict):
        global_options = {}

    mods = data_block.get("modifications")

    if not isinstance(mods, list):
        main_mod = data_block.get("modification")
        mods = [main_mod] if isinstance(main_mod, dict) else []

    main_mod = data_block.get("modification", {}) or {}

    rows = []

    for mod in mods:
        if not isinstance(mod, dict):
            continue

        price_raw = mod.get("price")
        cost_raw = mod.get("cost")

        if cost_raw in [None, "", 0, "0"]:
            cost_raw = main_mod.get("cost")

        price = clean_decimal(price_raw)

        if price is None:
            price = clean_decimal(cost_raw)

        image = None

        thumbs = mod.get("thumbs", {})

        if isinstance(thumbs, dict):
            main = thumbs.get("main", [])

            if main and isinstance(main, list):
                image = urljoin(BASE_URL, main[0])

        if not image:
            api_image = mod.get("image")

            if api_image:
                image = urljoin(BASE_URL, api_image)

        color_val = clean_text(global_options.get("size")) or color
        prop_val = clean_text(global_options.get("ispolnenie")) or properties_price

        additional_property = join_additional_property(
            color=color_val,
            properties_price=prop_val,
        )

        value_added_tax, final_price = calc_vat_and_final_price(price)

        rows.append(
            {
                "price": price,
                "value_added_tax": value_added_tax,
                "final_price": final_price,
                "additional_property": additional_property,
                "image": image,
            }
        )

    return rows


def save_product_data(
    product_url: ParserProductUrl,
    price_rows: list[dict],
    properties: list[dict],
    base_data: dict,
    *, workspace=None,
) -> dict:
    ParserProductProperty = workspace.model("ParserProductProperty") if workspace else globals()["ParserProductProperty"]
    TtProductPrice = workspace.model("TtProductPrice") if workspace else globals()["TtProductPrice"]
    product_key = product_url.id
    today = timezone.localdate() if workspace else date.today()
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

    price_objects = []

    for row in price_rows:
        image = row.get("image") or base_data.get("image")
        additional_property = row.get("additional_property") or product_url.additional_property

        price_objects.append(
            TtProductPrice(
                product_key=product_key,
                url=product_url.url,
                price=row.get("price"),
                value_added_tax=row.get("value_added_tax"),
                final_price=row.get("final_price"),
                additional_property=additional_property,
                image=image,
                name=base_data.get("name"),
            )
        )

    if not price_objects:
        price_objects.append(
            TtProductPrice(
                product_key=product_key,
                url=product_url.url,
                price=None,
                value_added_tax=None,
                final_price=None,
                additional_property=product_url.additional_property,
                image=base_data.get("image"),
                name=base_data.get("name"),
            )
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

        TtProductPrice.objects.filter(
            product_key=product_key,
            date_add__date=today,
        ).delete()

        if price_objects:
            TtProductPrice.objects.bulk_create(
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


def mark_url_failed(product_url_id: int, error: Exception, *, workspace=None) -> None:
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    ParserProductUrl.objects.filter(id=product_url_id).update(
        is_loaded=False,
        last_error=str(error),
        date_update=timezone.now(),
    )


def mark_url_not_found(product_url_id: int, error: Exception, *, workspace=None) -> None:
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    ParserProductUrl.objects.filter(id=product_url_id).update(
        status=ParserProductUrl.STATUS_INACTIVE,
        is_loaded=False,
        last_error=str(error),
        date_update=timezone.now(),
    )


def parse_one_url(product_url_id: int, *, workspace=None) -> dict:
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    product_url = ParserProductUrl.objects.get(id=product_url_id)

    logger.info(
        "TT parsing product_url_id=%s url=%s additional_property=%s",
        product_url.id,
        product_url.url,
        product_url.additional_property,
    )

    html = fetch_html(product_url.url)
    base_data = parse_base_product_data(html)

    rid = base_data.get("rid")

    if not rid:
        raise TtRequestError("RID not found")

    color, properties_price = split_additional_property(
        product_url.additional_property,
    )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
        }
    )

    price_rows = fetch_modification_data(
        session=session,
        rid=rid,
        color=color,
        properties_price=properties_price,
    )

    properties = parse_properties_from_soup(base_data["soup"])

    saved = save_product_data(
        product_url=product_url,
        price_rows=price_rows,
        properties=properties,
        base_data=base_data,
        workspace=workspace,
    )

    return {
        "product_url_id": product_url.id,
        "product_key": product_url.id,
        "properties": saved["properties"],
        "prices": saved["prices"],
    }


@standalone("tt")
def parse_tt_products(
    limit: int | None = None,
    retry_failed: bool = False,
    blocked_only: bool = False,
    workers: int | None = None,
    product_keys: set[int] | None = None,
    *, workspace=None,
) -> dict:
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    workers = workers or settings.TARA_PARSER_WORKERS
    today = timezone.localdate() if workspace else date.today()

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
            "TT products parsing started: "
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
            executor.submit(parse_one_url, product_url_id, workspace=workspace): product_url_id
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
                    "TT product parsed: product_url_id=%s product_key=%s properties=%s prices=%s",
                    result["product_url_id"],
                    result["product_key"],
                    result["properties"],
                    result["prices"],
                )

            except TtNotFoundError as exc:
                failed += 1
                not_found += 1

                mark_url_not_found(product_url_id, exc, workspace=workspace)

                logger.warning(
                    "TT product not found: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

            except TtBlockedError as exc:
                failed += 1
                blocked += 1

                mark_url_failed(product_url_id, exc, workspace=workspace)

                logger.warning(
                    "TT product blocked: product_url_id=%s error=%s",
                    product_url_id,
                    exc,
                )

            except Exception as exc:
                failed += 1

                mark_url_failed(product_url_id, exc, workspace=workspace)

                logger.exception(
                    "TT product parse failed: product_url_id=%s error=%s",
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

    logger.info("TT products parsing finished: %s", result)

    return result