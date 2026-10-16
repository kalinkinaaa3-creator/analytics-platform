from .queue_execution import standalone
import logging
from itertools import product
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from django.db import transaction

from datasets.models import ParserPrefix, ParserProductUrl


logger = logging.getLogger("parsers.tt")

SOURCE = "tt"
BASE_URL = "https://toptara.ru"
CATALOG_URL = f"{BASE_URL}/katalog/"
MISSING_FROM_MAP = "missing_from_map"

MAX_CATEGORY_PAGES = 100


class TtPageNotFoundError(Exception):
    pass


class TtBlockedError(Exception):
    pass


def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def normalize_url(url):
    url = clean_value(url)
    if not url:
        return None

    parsed = urlparse(url)
    path = parsed.path or "/"

    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            path,
            "",
            parsed.query or "",
            "",
        )
    )


def normalize_additional_property(color, properties_price):
    color = clean_value(color)
    properties_price = clean_value(properties_price)

    parts = [item for item in (color, properties_price) if item]

    if not parts:
        return None

    return "/".join(parts)


def fetch_html(url):
    logger.info("TT request: %s", url)

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
    lower_html = html.lower()

    logger.info(
        "TT response: status=%s html_len=%s url=%s final_url=%s",
        status,
        len(html),
        url,
        response.url,
    )

    if status == 404:
        raise TtPageNotFoundError(f"HTTP 404: page not found: {url}")

    if status in (401, 403):
        raise TtBlockedError(f"HTTP {status}: blocked by TT server: {url}")

    if status >= 500:
        raise RuntimeError(f"HTTP {status}: TT server error: {url}")

    if "access denied" in lower_html or "request blocked" in lower_html:
        raise TtBlockedError(f"Blocked by TT server content: {url}")

    if "страница не найдена" in lower_html or "page not found" in lower_html:
        raise TtPageNotFoundError(f"Not found content: {url}")

    return html


def extract_category_urls():
    html = fetch_html(CATALOG_URL)
    soup = BeautifulSoup(html, "html.parser")

    catalog_block = soup.select_one(".mini_catalog_body")

    if not catalog_block:
        raise RuntimeError("TT catalog block not found")

    result = []
    seen = set()

    for item in catalog_block.select(".element_catalog_block"):
        link = item.select_one("a.title_catalog_block")

        if not link:
            continue

        href = link.get("href")

        if not href:
            continue

        full_url = normalize_url(urljoin(BASE_URL, href))

        if not full_url:
            continue

        if full_url.rstrip("/") == CATALOG_URL.rstrip("/"):
            continue

        if full_url in seen:
            continue

        seen.add(full_url)

        category_name = clean_value(link.get_text(" ", strip=True))

        if not category_name:
            img = item.select_one("img")
            category_name = clean_value(img.get("alt")) if img else None

        result.append(
            {
                "category": category_name,
                "url": full_url,
            }
        )

    logger.info("TT categories found: count=%s", len(result))

    for item in result:
        logger.info("TT category: name=%s url=%s", item["category"], item["url"])

    return result


def get_product_items(soup):
    products = soup.select("ul#lse2_results li.item")

    if products:
        return products

    products = soup.select("ul#ms2_results li.item")

    if products:
        return products

    return [
        item
        for item in soup.select("li.item")
        if item.select_one(".item-title a")
    ]


def extract_product_url_from_item(product_item):
    link_tag = product_item.select_one(".item-title a")

    if not link_tag:
        return None

    href = link_tag.get("href")

    if not href:
        return None

    full_url = normalize_url(urljoin(BASE_URL, href))

    if not full_url:
        return None

    parsed = urlparse(full_url)

    if not parsed.netloc.endswith("toptara.ru"):
        return None

    if "/katalog/" not in parsed.path:
        return None

    return full_url


def extract_last_page_number(soup):
    page_numbers = {1}

    for link in soup.select("a[href*='page=']"):
        href = link.get("href")

        if not href:
            continue

        parsed = urlparse(href)
        query = parse_qs(parsed.query)

        raw_page = query.get("page", [None])[0]

        if not raw_page:
            continue

        try:
            page_num = int(raw_page)
        except (TypeError, ValueError):
            continue

        if page_num > 0:
            page_numbers.add(page_num)

    for item in soup.select("[data-page]"):
        raw_page = item.get("data-page")

        try:
            page_num = int(raw_page)
        except (TypeError, ValueError):
            continue

        if page_num > 0:
            page_numbers.add(page_num)

    return max(page_numbers)


def extract_product_urls_from_category(category_url):
    result = []
    seen_product_urls = set()
    seen_page_signatures = set()

    first_html = None
    last_page = 1

    page_num = 1

    while page_num <= min(last_page, MAX_CATEGORY_PAGES):
        page_url = category_url if page_num == 1 else f"{category_url}?page={page_num}"

        logger.info("TT category page: %s", page_url)

        try:
            html = first_html if first_html and page_num == 1 else fetch_html(page_url)
        except TtPageNotFoundError as exc:
            logger.warning(
                "TT category skipped: page not found category_url=%s page=%s error=%s",
                category_url,
                page_num,
                exc,
            )
            break

        soup = BeautifulSoup(html, "html.parser")

        if page_num == 1:
            last_page = extract_last_page_number(soup)
            first_html = html

            logger.info(
                "TT category pagination detected: category_url=%s last_page=%s",
                category_url,
                last_page,
            )

        products = get_product_items(soup)

        if not products:
            logger.info(
                "TT category pagination stopped: no products category_url=%s page=%s",
                category_url,
                page_num,
            )
            break

        page_product_urls = []

        for product_item in products:
            product_url = extract_product_url_from_item(product_item)

            if product_url:
                page_product_urls.append(product_url)

        if not page_product_urls:
            logger.info(
                "TT category pagination stopped: no valid product urls category_url=%s page=%s",
                category_url,
                page_num,
            )
            break

        page_signature = tuple(sorted(set(page_product_urls)))

        if page_signature in seen_page_signatures:
            logger.info(
                "TT category pagination stopped: repeated page category_url=%s page=%s products=%s",
                category_url,
                page_num,
                len(page_signature),
            )
            break

        seen_page_signatures.add(page_signature)

        added_on_page = 0
        duplicate_on_page = 0

        for product_url in page_product_urls:
            if product_url in seen_product_urls:
                duplicate_on_page += 1
                continue

            seen_product_urls.add(product_url)
            result.append(product_url)
            added_on_page += 1

        logger.info(
            "TT products found on page: category_url=%s page=%s/%s total_on_page=%s added=%s duplicate=%s",
            category_url,
            page_num,
            last_page,
            len(page_product_urls),
            added_on_page,
            duplicate_on_page,
        )

        if added_on_page == 0:
            logger.info(
                "TT category pagination stopped: no new products category_url=%s page=%s",
                category_url,
                page_num,
            )
            break

        page_num += 1

    if page_num > MAX_CATEGORY_PAGES:
        logger.warning(
            "TT category pagination stopped by MAX_CATEGORY_PAGES=%s category_url=%s",
            MAX_CATEGORY_PAGES,
            category_url,
        )

    return result


def extract_variations_from_product_html(html):
    soup = BeautifulSoup(html, "html.parser")

    colors = []
    properties_prices = []

    color_select = soup.select_one("select[name='options[size]']")

    if color_select:
        for option in color_select.select("option"):
            value = clean_value(option.get("value"))

            if value:
                colors.append(value)

    for radio in soup.select("input[type='radio'][name^='options']"):
        name = radio.get("name") or ""

        if "ispolnenie" not in name:
            continue

        value = clean_value(radio.get("value"))

        if value:
            properties_prices.append(value)

    if not colors:
        colors = [None]

    if not properties_prices:
        properties_prices = [None]

    variations = []
    seen = set()

    for color, properties_price in product(colors, properties_prices):
        additional_property = normalize_additional_property(
            color=color,
            properties_price=properties_price,
        )

        if additional_property in seen:
            continue

        seen.add(additional_property)

        variations.append(
            {
                "color": color,
                "properties_price": properties_price,
                "additional_property": additional_property,
            }
        )

    if not variations:
        variations.append(
            {
                "color": None,
                "properties_price": None,
                "additional_property": None,
            }
        )

    return variations


@standalone("links")
def sync_tt_product_urls(*, workspace=None):
    ParserPrefix = workspace.model("ParserPrefix") if workspace else globals()["ParserPrefix"]
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    prefixes = list(
        ParserPrefix.objects.filter(source=SOURCE)
        .order_by("id")
        .values_list("prefix", flat=True)
    )

    if not prefixes:
        prefixes = ["-"]

    active_ids = set()

    created = 0
    updated = 0
    inactivated = 0
    skipped = 0
    product_failed = 0
    product_not_found = 0

    total_categories = 0
    total_product_urls = 0
    total_variations = 0

    with transaction.atomic():
        categories = extract_category_urls()
        total_categories = len(categories)

        for category in categories:
            product_urls = extract_product_urls_from_category(category["url"])
            total_product_urls += len(product_urls)

            logger.info(
                "TT category completed: name=%s url=%s product_urls=%s",
                category["category"],
                category["url"],
                len(product_urls),
            )

            for product_url in product_urls:
                try:
                    html = fetch_html(product_url)
                    variations = extract_variations_from_product_html(html)
                except TtPageNotFoundError as exc:
                    product_not_found += 1
                    logger.warning(
                        "TT product skipped as not found: url=%s error=%s",
                        product_url,
                        exc,
                    )
                    continue
                except Exception as exc:
                    product_failed += 1
                    logger.exception(
                        "TT product variation extraction failed: url=%s error=%s",
                        product_url,
                        exc,
                    )
                    continue

                total_variations += len(variations)

                for variation in variations:
                    obj, is_created = ParserProductUrl.objects.update_or_create(
                        source=SOURCE,
                        url=product_url,
                        additional_property=variation["additional_property"],
                        defaults={
                            "prefix": prefixes[0],
                            "status": ParserProductUrl.STATUS_ACTIVE,
                            "last_error": None,
                        },
                    )

                    active_ids.add(obj.id)

                    if is_created:
                        created += 1
                    else:
                        updated += 1

        if workspace and (not active_ids or product_failed):
            raise RuntimeError("Incomplete TT catalog; existing links preserved")

        inactive_qs = ParserProductUrl.objects.filter(
            source=SOURCE,
        ).exclude(
            id__in=active_ids,
        )

        inactivated = inactive_qs.update(
            status=ParserProductUrl.STATUS_INACTIVE,
            last_error=MISSING_FROM_MAP,
        )

    result = {
        "prefixes": len(prefixes),
        "categories": total_categories,
        "product_urls_found": total_product_urls,
        "variations_found": total_variations,
        "active_urls": len(active_ids),
        "created": created,
        "updated": updated,
        "inactivated": inactivated,
        "skipped": skipped,
        "product_not_found": product_not_found,
        "product_failed": product_failed,
    }

    logger.info("TT product URL sync finished: %s", result)

    return result