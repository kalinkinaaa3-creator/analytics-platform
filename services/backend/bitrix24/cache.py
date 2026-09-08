import hashlib
import json

from django.core.cache import cache


BITRIX24_CACHE_PREFIX = "bitrix24:response"
BITRIX24_CACHE_TIMEOUT = 60 * 15


def dashboard_cache_key(payload) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{BITRIX24_CACHE_PREFIX}:dashboard:v12:{digest}"


def get_dashboard_cache(payload):
    return cache.get(dashboard_cache_key(payload))


def set_dashboard_cache(payload, value, *, timeout=BITRIX24_CACHE_TIMEOUT):
    cache.set(dashboard_cache_key(payload), value, timeout=timeout)


def invalidate_bitrix24_cache():
    delete_pattern = getattr(cache, "delete_pattern", None)
    if delete_pattern is not None:
        delete_pattern(f"{BITRIX24_CACHE_PREFIX}:*")
