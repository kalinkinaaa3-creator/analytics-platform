import hashlib
import json

from django.core.cache import cache


def chart_cache_key(dataset_id, chart_type, params):

    raw = f"{dataset_id}:{chart_type}:{json.dumps(params, sort_keys=True)}"

    return "chart:" + hashlib.md5(raw.encode()).hexdigest()