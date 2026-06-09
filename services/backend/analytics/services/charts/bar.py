from collections import defaultdict
from analytics.services.aggregations.base import get_dataset_data


def build_bar_chart(dataset_id: int, x_field: str, y_field: str):

    data = get_dataset_data(dataset_id)

    result = defaultdict(int)

    for row in data:
        x = row.get(x_field)
        y = row.get(y_field)

        try:
            y = float(y)
        except:
            y = 0

        result[x] += y

    return {
        "type": "bar",
        "x": list(result.keys()),
        "y": list(result.values())
    }