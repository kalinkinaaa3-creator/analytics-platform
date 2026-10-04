from django.core.cache import cache


def dashboard_cache_key(dashboard_id: int | str, organization_id=None) -> str:
    from organizations.models import legacy_organization_id
    if organization_id is None:
        organization_id = legacy_organization_id()
    return f"dashboard:org:{organization_id}:{dashboard_id}"


def user_dashboard_cache_key(user_id: int, dashboard_id: int) -> str:
    return dashboard_cache_key(f"user:{user_id}:dashboard:{dashboard_id}", _dashboard_org(dashboard_id))


def _dashboard_org(dashboard_id):
    from dashboards.models import Dashboard
    return Dashboard.objects.values_list("organization_id", flat=True).get(pk=dashboard_id)


def get_dashboard_cache(dashboard_id: int | str):
    key = dashboard_cache_key(dashboard_id, _dashboard_org(dashboard_id))
    return cache.get(key)


def set_dashboard_cache(dashboard_id: int | str, value: dict):
    key = dashboard_cache_key(dashboard_id, _dashboard_org(dashboard_id))
    cache.set(key, value, timeout=60 * 5)


def get_cache_by_key(key: str):
    return cache.get(key)


def set_cache_by_key(key: str, value: dict):
    cache.set(key, value, timeout=60 * 5)


def delete_dashboard_cache_for_user(user_id: int, dashboard_id: int):
    key = dashboard_cache_key(
        f"user:{user_id}:dashboard:{dashboard_id}", _dashboard_org(dashboard_id),
    )
    cache.delete(key)


def delete_dashboard_cache(dashboard_id: int):
    key = dashboard_cache_key(dashboard_id, _dashboard_org(dashboard_id))
    cache.delete(key)


def delete_dashboard_cache_patterns(dashboard_id: int, user_id: int | None = None):
    prefix = f"dashboard:org:{_dashboard_org(dashboard_id)}"
    if user_id:
        cache.delete_pattern(
            f"*{prefix}:user:{user_id}:dashboard:{dashboard_id}:filters:*"
        )

    cache.delete_pattern(
        f"*{prefix}:user:*:dashboard:{dashboard_id}:filters:*"
    )

    cache.delete_pattern(
        f"*{prefix}:dashboard:{dashboard_id}:filters:*"
    )
