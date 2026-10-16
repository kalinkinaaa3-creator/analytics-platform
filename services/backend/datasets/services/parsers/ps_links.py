from .queue_execution import standalone
import logging
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.db import transaction

from datasets.models import ParserPrefix, ParserProductUrl


logger = logging.getLogger("parsers.ps")

SOURCE = "ps"
BASE_DOMAIN = "plastic-system.ru"
MISSING_FROM_MAP = "missing_from_map"


class PsPageNotFoundError(Exception):
    pass


class PsBlockedError(Exception):
    pass


def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def normalize_prefix(prefix):
    prefix = clean_value(prefix)

    if not prefix:
        return None

    prefix = prefix.lower()
    prefix = prefix.replace("https://", "")
    prefix = prefix.replace("http://", "")
    prefix = prefix.replace(f".{BASE_DOMAIN}", "")
    prefix = prefix.strip("/").strip(".")

    return prefix or None


def build_base_url(prefix):
    prefix = normalize_prefix(prefix)

    if not prefix:
        raise ValueError(f"Invalid PS prefix: {prefix}")

    if prefix == "spb_withoutprefix":
        return f"https://{BASE_DOMAIN}"

    return f"https://{prefix}.{BASE_DOMAIN}"


def is_not_found_content(html):
    lower_html = str(html or "").lower()

    return (
        "страница в каталоге не найдена" in lower_html
        or "страница не найдена" in lower_html
        or "page not found" in lower_html
        or "not found" in lower_html
    )


def fetch_html(url):
    logger.info("PS request: %s", url)

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

    html = response.text or ""
    status = response.status_code

    logger.info(
        "PS response: status=%s html_len=%s url=%s",
        status,
        len(html),
        url,
    )

    if status == 404:
        raise PsPageNotFoundError(f"HTTP 404: page not found: {url}")

    if status in (401, 403):
        raise PsBlockedError(f"HTTP {status}: blocked by PS server: {url}")

    if status >= 500:
        raise RuntimeError(f"HTTP {status}: PS server error: {url}")

    lower_html = html.lower()

    if "access denied" in lower_html or "request blocked" in lower_html:
        raise PsBlockedError(f"Blocked by PS server content: {url}")

    if is_not_found_content(html):
        raise PsPageNotFoundError(f"Not found content: {url}")

    return html


def extract_category_urls(base_url):
    html = fetch_html(base_url)
    soup = BeautifulSoup(html, "html.parser")

    category_links = soup.select("a[href*='/product-category/']")

    result = []
    seen = set()

    for link in category_links:
        href = link.get("href")

        if not href:
            continue

        full_url = urljoin(base_url, href).rstrip("/")

        if full_url.rstrip("/") == f"{base_url}/product-category":
            continue

        if full_url in seen:
            continue

        seen.add(full_url)

        title_el = link.select_one(".text-center")
        category_name = title_el.get_text(strip=True) if title_el else None

        if not category_name:
            img = link.select_one("img")
            category_name = img.get("alt") if img else None

        category_name = clean_value(category_name)

        result.append(
            {
                "category": category_name,
                "url": full_url,
            }
        )

    logger.info("PS categories found: count=%s", len(result))

    for item in result:
        logger.info(
            "PS category: name=%s url=%s",
            item["category"],
            item["url"],
        )

    return result


def extract_product_urls_from_category(category_url, base_url, *, strict=False):
    result = []
    seen = set()

    page_num = 1

    while True:
        page_url = category_url if page_num == 1 else f"{category_url}?PAGEN_3={page_num}"

        logger.info("PS category page: %s", page_url)

        try:
            html = fetch_html(page_url)
        except PsPageNotFoundError as exc:
            if strict and page_num == 1:
                raise
            logger.warning(
                "PS category skipped: page not found category_url=%s page=%s error=%s",
                category_url,
                page_num,
                exc,
            )
            break
        except PsBlockedError:
            raise
        except Exception as exc:
            if strict:
                raise
            logger.exception(
                "PS category page failed: category_url=%s page=%s error=%s",
                category_url,
                page_num,
                exc,
            )
            break

        soup = BeautifulSoup(html, "html.parser")

        products = soup.select("div.product-item-title")

        if not products:
            logger.info(
                "PS category pagination stopped: no products category_url=%s page=%s",
                category_url,
                page_num,
            )
            break

        found_on_page = 0

        for product in products:
            link_tag = product.select_one("a.item_title")

            if not link_tag:
                continue

            href = link_tag.get("href")

            if not href:
                continue

            full_url = urljoin(base_url, href)

            parsed = urlparse(full_url)
            base_product_url = parsed._replace(query="").geturl()

            parent = product.find_parent()
            status_block = parent.select_one("div[id^='status_amount_']") if parent else None

            oids = set()

            query_params = parse_qs(parsed.query)

            if "oid" in query_params:
                oids.add(query_params["oid"][0])

            if status_block:
                spans = status_block.select("span[id^='status_value_']")

                for span in spans:
                    span_id = span.get("id")

                    if not span_id:
                        continue

                    oid = span_id.replace("status_value_", "")

                    if oid.isdigit():
                        oids.add(oid)

            if not oids:
                final_url = base_product_url

                if final_url not in seen:
                    seen.add(final_url)
                    result.append(final_url)
                    found_on_page += 1

                continue

            for oid in oids:
                final_url = f"{base_product_url}?oid={oid}"

                if final_url in seen:
                    continue

                seen.add(final_url)
                result.append(final_url)
                found_on_page += 1

        logger.info(
            "PS products found on page: category_url=%s page=%s count=%s",
            category_url,
            page_num,
            found_on_page,
        )

        if found_on_page == 0:
            break

        page_num += 1

    return result


@standalone("links")
def sync_ps_product_urls(*, workspace=None):
    ParserPrefix = workspace.model("ParserPrefix") if workspace else globals()["ParserPrefix"]
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    prefixes = list(
        ParserPrefix.objects.filter(source=SOURCE)
        .order_by("id")
        .values_list("prefix", flat=True)
    )

    if not prefixes:
        raise RuntimeError("No parser prefixes found for source=ps")

    active_ids = set()

    created = 0
    updated = 0
    inactivated = 0
    skipped = 0
    category_not_found = 0
    category_failed = 0

    total_categories = 0
    total_product_urls = 0

    with transaction.atomic():
        for raw_prefix in prefixes:
            prefix = normalize_prefix(raw_prefix)

            if not prefix:
                skipped += 1
                continue

            base_url = build_base_url(prefix)

            try:
                categories = extract_category_urls(base_url)
            except Exception as exc:
                logger.exception(
                    "PS prefix failed: prefix=%s base_url=%s error=%s",
                    prefix,
                    base_url,
                    exc,
                )
                skipped += 1
                continue

            if workspace and not categories:
                raise RuntimeError("Empty PS regional catalog; existing links preserved")
            total_categories += len(categories)

            for category in categories:
                try:
                    product_urls = extract_product_urls_from_category(
                        category_url=category["url"],
                        base_url=base_url,
                        strict=workspace is not None,
                    )
                except PsPageNotFoundError as exc:
                    category_not_found += 1
                    logger.warning(
                        "PS category skipped as not found: name=%s url=%s error=%s",
                        category["category"],
                        category["url"],
                        exc,
                    )
                    continue
                except Exception as exc:
                    category_failed += 1
                    logger.exception(
                        "PS category failed: name=%s url=%s error=%s",
                        category["category"],
                        category["url"],
                        exc,
                    )
                    continue

                total_product_urls += len(product_urls)

                for product_url in product_urls:
                    obj, is_created = ParserProductUrl.objects.update_or_create(
                        source=SOURCE,
                        url=product_url,
                        additional_property=None,
                        defaults={
                            "prefix": prefix,
                            "status": ParserProductUrl.STATUS_ACTIVE,
                            "last_error": None,
                        },
                    )

                    active_ids.add(obj.id)

                    if is_created:
                        created += 1
                    else:
                        updated += 1

        if workspace and (not active_ids or skipped or category_failed or category_not_found):
            raise RuntimeError("Incomplete PS catalog; existing links preserved")

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
        "category_not_found": category_not_found,
        "category_failed": category_failed,
        "product_urls_found": total_product_urls,
        "active_urls": len(active_ids),
        "created": created,
        "updated": updated,
        "inactivated": inactivated,
        "skipped": skipped,
    }

    logger.info("PS product URL sync finished: %s", result)

    return result