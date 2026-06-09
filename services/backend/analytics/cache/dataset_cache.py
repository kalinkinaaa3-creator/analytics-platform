import json

from django.core.cache import cache


def cache_key(dataset_id: int):
    return f"dataset:stats:{dataset_id}"