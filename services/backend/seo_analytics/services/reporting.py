import hashlib
import json

from django.conf import settings
from django.core.cache import cache

from seo_analytics.models import SeoBrandMask, SeoGoal
from seo_analytics.services.warehouse_reporting import build_report


SUPPORTED_PAGES = {
    "visits", "new-visitors", "returning-visitors", "search-phrases",
    "traffic-change", "conversions", "unique-conversions", "landing-pages",
    "calltouch", "positions", "competitors",
}


def _hash(page, filters):
    configuration = {}
    if page in {"conversions", "unique-conversions"}:
        configuration["goals"] = list(
            SeoGoal.objects.filter(is_active=True, is_available=True)
            .order_by("position", "id")
            .values_list("external_id", "name", "position", "date_update")
        )
    if page in {"search-phrases", "conversions", "unique-conversions"}:
        configuration["brand_masks"] = list(
            SeoBrandMask.objects.filter(is_active=True)
            .order_by("mask")
            .values_list("mask", "date_update")
        )
    raw = json.dumps(
        {"page": page, "filters": filters, "configuration": configuration},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_report(page, filters):
    if page == "calltouch":
        return {"availability": "planned", "message": "Раздел будет доступен после подключения Calltouch.", "cards": {}, "charts": {}, "tables": {}, "quality": []}
    if page in {"positions", "competitors"}:
        message = "Раздел конкурентов будет подключён отдельным этапом." if page == "competitors" else "Раздел позиций будет подключён отдельным этапом."
        return {"availability": "planned", "message": message, "cards": {}, "charts": {}, "tables": {}, "quality": []}

    cache_version = "v7" if page == "landing-pages" else "v5" if page in {"visits", "new-visitors", "returning-visitors", "traffic-change", "unique-conversions"} else "v3"
    cache_key = f"seo:report:{cache_version}:{page}:{_hash(page, filters)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        payload = build_report(page, filters)
    except Exception as exc:
        return {
            "availability": "not_ready",
            "message": f"Локальная SEO-витрина ещё не подготовлена: {exc}",
            "cards": {}, "charts": {}, "tables": {}, "quality": [],
            "meta": {"page": page, "date_from": filters["date_from"], "date_to": filters["date_to"]},
        }
    cache.set(cache_key, payload, timeout=settings.SEO_REPORT_CACHE_TIMEOUT)
    return payload
