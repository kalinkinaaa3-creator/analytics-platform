import json

from analytics.clickhouse.client import get_clickhouse_client
from analytics.clickhouse.schema import ensure_dataset_rows_table


class ClickHouseRepository:

    def insert_dataset_rows(self, dataset_id: int, rows: list):
        ensure_dataset_rows_table()

        client = get_clickhouse_client()

        payload = [
            (
                dataset_id,
                json.dumps(row)
            )
            for row in rows
        ]

        if not payload:
            return

        client.execute(
            """
            INSERT INTO default.dataset_rows
            (dataset_id, data)
            VALUES
            """,
            payload,
        )

    def fetch_dataset_rows(self, dataset_id: int):
        ensure_dataset_rows_table()

        client = get_clickhouse_client()

        rows = client.execute(
            """
            SELECT data
            FROM default.dataset_rows
            WHERE dataset_id = %(dataset_id)s
            """,
            {"dataset_id": dataset_id},
        )

        return [
            json.loads(row[0])
            for row in rows
        ]