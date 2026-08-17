import secrets

from django.core.cache import cache


SELECTION_TTL_SECONDS = 60 * 60
SELECTION_KEY_PREFIX = "iprice:analytics-selection:v1"


def _cache_key(token):
    return f"{SELECTION_KEY_PREFIX}:{token}"


def create_analytics_selection(*, user, snapshot, product_keys, context):
    token = secrets.token_urlsafe(24)
    payload = {
        "user_id": user.pk,
        "snapshot_id": snapshot.pk,
        "product_keys": list(product_keys),
        "context": context,
    }
    cache.set(_cache_key(token), payload, SELECTION_TTL_SECONDS)
    return token, payload


def get_analytics_selection(*, user, token):
    payload = cache.get(_cache_key(token))
    if not payload or payload.get("user_id") != user.pk:
        return None
    return payload
