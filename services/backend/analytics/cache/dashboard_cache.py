from django.core.cache import cache


def dashboard_cache_key(dashboard_id: int):
    return f"dashboard:v3:{dashboard_id}"


def get_dashboard_cache(dashboard_id: int):
    return cache.get(
        dashboard_cache_key(dashboard_id)
    )


def set_dashboard_cache(dashboard_id: int, data: dict):
    cache.set(
        dashboard_cache_key(dashboard_id),
        data,
        timeout=300
    )