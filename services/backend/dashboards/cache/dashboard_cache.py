from django.core.cache import cache


def dashboard_cache_key(dashboard_id: int | str) -> str:
    return f"dashboard:{dashboard_id}"


def user_dashboard_cache_key(user_id: int, dashboard_id: int) -> str:
    return f"dashboard:user:{user_id}:dashboard:{dashboard_id}"


def get_dashboard_cache(dashboard_id: int | str):
    key = dashboard_cache_key(dashboard_id)
    return cache.get(key)


def set_dashboard_cache(dashboard_id: int | str, value: dict):
    key = dashboard_cache_key(dashboard_id)
    cache.set(key, value, timeout=60 * 5)


def get_cache_by_key(key: str):
    return cache.get(key)


def set_cache_by_key(key: str, value: dict):
    cache.set(key, value, timeout=60 * 5)


def delete_dashboard_cache_for_user(user_id: int, dashboard_id: int):
    key = dashboard_cache_key(
        f"user:{user_id}:dashboard:{dashboard_id}"
    )
    cache.delete(key)


def delete_dashboard_cache(dashboard_id: int):
    key = dashboard_cache_key(dashboard_id)
    cache.delete(key)