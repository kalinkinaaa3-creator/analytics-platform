from datasets.models import DatasetRow
from analytics.cache.dataset_cache import (
    cache_key
)
from django.core.cache import cache


def dataset_statistics(dataset_id: int):

    key = cache_key(dataset_id)

    cached = cache.get(key)

    if cached:
        return cached

    rows = DatasetRow.objects.filter(
        dataset_id=dataset_id
    )

    data = [r.data for r in rows]

    result = {
        "dataset_id": dataset_id,
        "rows_count": len(data),
        "columns": list(data[0].keys()) if data else [],
        "sample_row": data[0] if data else None,
    }

    cache.set(key, result, timeout=300)

    return result