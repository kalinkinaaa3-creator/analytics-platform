import json
from analytics.clickhouse.repository import ClickHouseRepository


class AnalyticsEngine:

    def __init__(self):
        self.repo = ClickHouseRepository()

    def get_dataset_rows(self, dataset_id: int):
        raw_rows = self.repo.fetch_dataset_rows(dataset_id)

        parsed = []

        for row in raw_rows:
            parsed.append(json.loads(row[0]))

        return parsed

    def get_dataset_stats(self, dataset_id: int):
        rows = self.get_dataset_rows(dataset_id)

        return {
            "rows_count": len(rows)
        }