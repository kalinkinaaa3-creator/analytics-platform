import json

from analytics.clickhouse.repository import ClickHouseRepository


def get_dataset_rows(dataset_id: int):

    repo = ClickHouseRepository()

    rows = repo.fetch_dataset_rows(dataset_id)

    result = []

    for row in rows:
        result.append(json.loads(row[0]))

    return result