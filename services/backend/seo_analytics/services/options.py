from datetime import date

from django.conf import settings
from django.core.cache import cache

from seo_analytics.services.clickhouse import (
    CONVERSION_TABLE, LANDING_TABLE, PHRASE_TABLE, TRAFFIC_TABLE, ensure_seo_tables,
)


def _static_options():
    return {
        "devices": [],
        "search_engines": [],
        "regions": [],
        "robotness": [],
        "phrase_types": [
            {"id": "Брендовые", "name": "Брендовые"},
            {"id": "Небрендовые", "name": "Небрендовые"},
            {"id": "Не определено", "name": "Не определено"},
        ],
        "topvisor_configured": bool(
            settings.TOPVISOR_API_KEY and settings.TOPVISOR_PROJECT_ID
        ),
        "calltouch_configured": False,
        "metrika_configured": bool(
            settings.YANDEX_METRIKA_TOKEN and settings.YANDEX_METRIKA_COUNTER_ID
        ),
        "quality": [],
        "stale": False,
        "data_range": {"min_month": None, "max_month": None},
    }


def get_filter_options(filters=None, page=""):
    if filters is not None:
        return _dependent_options(filters, page)
    key = "seo:filter-options:v1"
    cached = cache.get(key)
    if cached is not None:
        return cached

    return refresh_filter_options()


def _dependent_options(filters, page):
    result = _static_options()
    if page == "search-phrases":
        table, columns = PHRASE_TABLE, ("search_engine", "robotness", "phrase_type")
    elif page in {"conversions", "unique-conversions"}:
        table, columns = CONVERSION_TABLE, ("device", "search_engine", "region", "phrase_type")
    elif page == "landing-pages":
        table, columns = LANDING_TABLE, ("device", "search_engine", "region")
    else:
        table, columns = TRAFFIC_TABLE, ("device", "search_engine", "region", "robotness")
    option_keys = {
        "device": "devices", "search_engine": "search_engines", "region": "regions",
        "robotness": "robotness", "phrase_type": "phrase_types",
    }
    client = ensure_seo_tables()
    min_month, max_month = client.execute(f"SELECT minOrNull(month),maxOrNull(month) FROM {table}")[0]
    result["data_range"] = {
        "min_month": min_month.isoformat() if min_month else None,
        "max_month": max_month.isoformat() if max_month else None,
    }
    for target in columns:
        clauses = ["month >= %(date_from)s", "month <= %(date_to)s"]
        query_params = {
            "date_from": date.fromisoformat(filters["date_from"]).replace(day=1),
            "date_to": date.fromisoformat(filters["date_to"]).replace(day=1),
        }
        for key in columns:
            values = tuple(filters.get(key) or ())
            if key != target and values:
                clauses.append(f"{key} IN %({key})s")
                query_params[key] = values
        rows = client.execute(
            f"SELECT {target},sum(visits) value FROM {table} WHERE {' AND '.join(clauses)} "
            f"GROUP BY {target} ORDER BY value DESC",
            query_params,
        )
        result[option_keys[target]] = [
            {"id": value or "Не определено", "name": value or "Не определено", "visits": int(visits or 0)}
            for value, visits in rows
        ]
    return result


def refresh_filter_options(client=None):
    key = "seo:filter-options:v1"
    result = _static_options()
    clickhouse = ensure_seo_tables()
    min_month, max_month = clickhouse.execute(
        f"SELECT minOrNull(month), maxOrNull(month) FROM {TRAFFIC_TABLE}"
    )[0]
    result["data_range"] = {
        "min_month": min_month.isoformat() if min_month else None,
        "max_month": max_month.isoformat() if max_month else None,
    }
    for option_key, column in {
        "devices": "device", "search_engines": "search_engine",
        "regions": "region", "robotness": "robotness",
    }.items():
        rows = clickhouse.execute(
            f"""SELECT {column}, sum(visits) value FROM {TRAFFIC_TABLE}
                GROUP BY {column} ORDER BY value DESC"""
        )
        result[option_key] = [
            {"id": value or "Не определено", "name": value or "Не определено", "visits": int(visits or 0)}
            for value, visits in rows
        ]
    cache.set(key, result, timeout=6 * 3600)
    return result
