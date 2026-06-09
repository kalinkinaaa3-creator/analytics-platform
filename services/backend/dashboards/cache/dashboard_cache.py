from django.core.cache import cache


def dashboard_cache_key(dashboard_id: int) -> str:
    return f"dashboard:{dashboard_id}"


def get_dashboard_cache(dashboard_id: int):
    key = dashboard_cache_key(dashboard_id)
    return cache.get(key)


def set_dashboard_cache(dashboard_id: int, value: dict):
    key = dashboard_cache_key(dashboard_id)
    cache.set(key, value, timeout=60 * 5)