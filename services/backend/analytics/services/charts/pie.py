from collections import defaultdict
from analytics.services.aggregations.base import get_dataset_data


def build_pie_chart(dataset_id: int, field: str):

    data = get_dataset_data(dataset_id)

    result = defaultdict(int)

    for row in data:
        key = row.get(field)
        result[key] += 1

    return {
        "type": "pie",
        "labels": list(result.keys()),
        "values": list(result.values())
    }