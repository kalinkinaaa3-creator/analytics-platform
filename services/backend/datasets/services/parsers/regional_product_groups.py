import re
from collections import defaultdict
from urllib.parse import unquote, urlsplit, urlunsplit

from datasets.models import ParserPrefix, ParserProductUrl


def _clean(value):
    value = "" if value is None else str(value).strip()
    return value or None


def _real_prefix(value):
    value = _clean(value)
    if not value or value == "-":
        return None
    value = value.casefold()
    return None if value.endswith("_withoutprefix") else value


def get_prefixes_by_source():
    result = defaultdict(set)
    rows = ParserPrefix.objects.exclude(
        source__isnull=True,
    ).exclude(source="").exclude(prefix__isnull=True).exclude(prefix="").values(
        "source", "prefix"
    )
    for row in rows:
        source = _clean(row["source"])
        prefix = _clean(row["prefix"])
        if source and prefix:
            result[source.casefold()].add(prefix.casefold())
    return result


def _normalized_url(url, prefixes):
    url = _clean(url)
    if not url:
        return None
    value = url if "://" in url else f"https://{url}"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    hostname = (parsed.hostname or "").casefold()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    real_prefixes = {_real_prefix(prefix) for prefix in prefixes} - {None}
    for prefix in sorted(real_prefixes, key=len, reverse=True):
        marker = f"{prefix}."
        if hostname.startswith(marker):
            hostname = hostname[len(marker):]
            break
    path = re.sub(r"/+", "/", unquote(parsed.path or "/"))
    parts = [part for part in path.split("/") if part]
    if parts and parts[0].casefold() in real_prefixes:
        parts = parts[1:]
    path = "/" + "/".join(parts) if parts else "/"
    normalized = urlunsplit(("", hostname, path.casefold(), parsed.query, ""))
    return normalized.lstrip("/") if hostname else None


def build_competitor_url_groups(*, prefixes_by_source):
    groups = defaultdict(set)
    group_by_product = {}
    if not prefixes_by_source:
        return groups, group_by_product
    rows = ParserProductUrl.objects.filter(
        status=ParserProductUrl.STATUS_ACTIVE,
        source__in=set(prefixes_by_source),
    ).exclude(source="base").only("id", "source", "url")
    for row in rows.iterator(chunk_size=1000):
        source = (_clean(row.source) or "").casefold()
        normalized = _normalized_url(row.url, prefixes_by_source.get(source, set()))
        if not normalized:
            continue
        key = (source, normalized)
        groups[key].add(row.id)
        group_by_product[row.id] = key
    return groups, group_by_product
