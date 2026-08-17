import hashlib
import json

from django.core.cache import cache


IPRICE_CACHE_TIMEOUT = 60 * 60 * 24
IPRICE_CACHE_PREFIX = "iprice:response"


def iprice_cache_key(
    scope: str,
    payload=None,
) -> str:
    serialized = json.dumps(
        payload or {},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    digest = hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()

    return (
        f"{IPRICE_CACHE_PREFIX}:"
        f"{scope}:{digest}"
    )


def get_iprice_cache(
    scope: str,
    payload=None,
):
    return cache.get(
        iprice_cache_key(
            scope,
            payload,
        )
    )


def set_iprice_cache(
    scope: str,
    payload,
    value,
    timeout: int = IPRICE_CACHE_TIMEOUT,
):
    cache.set(
        iprice_cache_key(
            scope,
            payload,
        ),
        value,
        timeout=timeout,
    )


def invalidate_iprice_cache():
    delete_pattern = getattr(
        cache,
        "delete_pattern",
        None,
    )

    if delete_pattern is not None:
        delete_pattern(
            f"{IPRICE_CACHE_PREFIX}:*"
        )