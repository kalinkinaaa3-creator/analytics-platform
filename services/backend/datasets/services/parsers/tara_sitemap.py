from .queue_execution import standalone
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import requests
from django.db import transaction
from django.utils import timezone

from datasets.models import ParserPrefix, ParserProductUrl


logger = logging.getLogger("parsers.tara")

SOURCE = "tara"
BASE_HOST = "tara.ru"
BASE_SCHEME = "https"
TARA_SITEMAP_URL = "https://tara.ru/sitemap-iblock-1013.xml"


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def parse_lastmod(value):
    value = clean_text(value)

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)

        return parsed
    except ValueError:
        return None


def normalize_prefix(prefix):
    prefix = clean_text(prefix)

    if not prefix:
        return None

    prefix = prefix.strip().lower()
    prefix = prefix.replace("https://", "")
    prefix = prefix.replace("http://", "")
    prefix = prefix.strip("/")

    if prefix.endswith(f".{BASE_HOST}"):
        prefix = prefix.replace(f".{BASE_HOST}", "")

    if prefix == BASE_HOST:
        return None

    prefix = prefix.rstrip(".")

    return prefix or None


def get_base_product_url(url):
    parsed = urlparse(url)

    path = parsed.path or ""

    if not path.startswith("/"):
        path = f"/{path}"

    return urlunparse(
        (
            BASE_SCHEME,
            BASE_HOST,
            path,
            "",
            parsed.query or "",
            "",
        )
    )


def build_prefixed_url(prefix, base_url):
    normalized_prefix = normalize_prefix(prefix)

    if not normalized_prefix:
        raise ValueError(f"Invalid parser prefix: {prefix}")

    parsed = urlparse(base_url)

    path = parsed.path or ""

    if not path.startswith("/"):
        path = f"/{path}"

    host = f"{normalized_prefix}.{BASE_HOST}"

    return urlunparse(
        (
            BASE_SCHEME,
            host,
            path,
            "",
            parsed.query or "",
            "",
        )
    )


def is_product_url(url):
    parsed = urlparse(url)
    path = parsed.path or ""

    if "/catalog/" not in path:
        return False

    ignored_parts = [
        "/filter/",
        "/compare/",
        "/personal/",
        "/basket/",
    ]

    return not any(part in path for part in ignored_parts)


def fetch_sitemap_xml(*, workspace=None, run_id=None, run_lease=None):
    from .tara_remote import fetch
    from .tara_product_parser import BrowserBlockedError, BrowserServiceError
    payload = fetch(TARA_SITEMAP_URL, workspace=workspace, run_id=run_id, run_lease=run_lease)
    if payload.get('status') in (401,403,429,502) or payload.get('blocked') or payload.get('error'):
        raise BrowserBlockedError('Windows sitemap access unavailable')
    if payload.get('status') != 200:
        raise BrowserServiceError('Sitemap unavailable')
    return payload.get('html', '').encode('utf-8')


def extract_urls_from_sitemap(xml_content):
    root = ET.fromstring(xml_content)

    namespace_match = re.match(r"\{.*\}", root.tag)
    namespace = namespace_match.group(0) if namespace_match else ""

    result = []

    for url_node in root.findall(f"{namespace}url"):
        loc_node = url_node.find(f"{namespace}loc")
        lastmod_node = url_node.find(f"{namespace}lastmod")

        if loc_node is None:
            continue

        loc = clean_text(loc_node.text)
        lastmod = parse_lastmod(lastmod_node.text if lastmod_node is not None else None)

        if not loc:
            continue

        if not is_product_url(loc):
            continue

        base_url = get_base_product_url(loc)

        result.append(
            {
                "base_url": base_url,
                "lastmod": lastmod,
            }
        )

    logger.info("Tara sitemap product urls extracted: %s", len(result))

    return result


@standalone("links")
def sync_tara_sitemap_to_product_urls(*, workspace=None, run_id=None, run_lease=None):
    ParserPrefix = workspace.model("ParserPrefix") if workspace else globals()["ParserPrefix"]
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    xml_content = fetch_sitemap_xml(workspace=workspace, run_id=run_id, run_lease=run_lease)
    sitemap_items = extract_urls_from_sitemap(xml_content)
    if not sitemap_items:
        raise RuntimeError('Sitemap contains no product URLs; existing links preserved')

    prefixes = []

    for raw_prefix in (
        ParserPrefix.objects.filter(source=SOURCE)
        .order_by("id")
        .values_list("prefix", flat=True)
    ):
        prefix = normalize_prefix(raw_prefix)

        if prefix:
            prefixes.append(prefix)

    if not prefixes:
        raise RuntimeError("No parser prefixes found for source=tara")

    active_ids = set()

    created = 0
    updated = 0
    inactivated = 0
    skipped = 0

    with transaction.atomic():
        if workspace and run_id is not None:
            owner = workspace.model('TaraRun').objects.select_for_update().get(pk=run_id)
            if owner.lease != run_lease or owner.status != 'running':
                raise RuntimeError('Tara sitemap owner changed; existing links preserved')
        for item in sitemap_items:
            base_url = item["base_url"]
            lastmod = item["lastmod"]

            for prefix in prefixes:
                try:
                    prefixed_url = build_prefixed_url(prefix, base_url)
                except ValueError:
                    skipped += 1
                    continue

                obj, is_created = ParserProductUrl.objects.update_or_create(
                    source=SOURCE,
                    url=prefixed_url,
                    additional_property=None,
                    defaults={
                        "prefix": prefix,
                        "status": ParserProductUrl.STATUS_ACTIVE,
                        "lastmod": lastmod,
                        "last_error": None,
                    },
                )

                active_ids.add(obj.id)

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
            last_error="missing_from_sitemap",
        )

    result = {
        "source_urls": len(sitemap_items),
        "prefixes": len(prefixes),
        "active_urls": len(active_ids),
        "created": created,
        "updated": updated,
        "inactivated": inactivated,
        "skipped": skipped,
    }

    logger.info("Tara sitemap sync finished: %s", result)

    return result
