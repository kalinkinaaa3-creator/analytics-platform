import hashlib
import json

from django.core.cache import cache
from django.conf import settings


CACHE_PREFIX = "leadgen"
REPORT_TIMEOUT = settings.LEAD_GENERATION_REPORT_CACHE_TIMEOUT
SOURCE_OPTIONS_TIMEOUT = settings.LEAD_GENERATION_REPORT_CACHE_TIMEOUT


def report_cache_key(page, filters, *, user_id=None, preference_version=""):
    payload = {
        "page": page,
        "filters": filters,
        "user_id": user_id if page == "sources" else None,
        "preference_version": preference_version if page == "sources" else "",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    return f"{CACHE_PREFIX}:report:v2:{page}:{digest}"


def invalidate_lead_generation_cache():
    delete_pattern = getattr(cache, "delete_pattern", None)
    if delete_pattern is not None:
        delete_pattern(f"{CACHE_PREFIX}:*")
