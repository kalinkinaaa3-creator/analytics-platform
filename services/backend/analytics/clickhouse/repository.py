import json

from analytics.clickhouse.client import get_clickhouse_client
from analytics.clickhouse.schema import (
    ensure_dataset_rows_table,
    ensure_fb_project_table,
)


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
    




    def truncate_fb_project(self):
        ensure_fb_project_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.fb_project
        """)

    def insert_fb_project_rows(self, rows: list[dict]):
        ensure_fb_project_table()

        client = get_clickhouse_client()

        payload = [
            (json.dumps(row, default=str),)
            for row in rows
        ]

        if not payload:
            return

        client.execute(
            """
            INSERT INTO default.fb_project
            (data)
            VALUES
            """,
            payload,
        )

    def fetch_fb_project_rows(self):
        ensure_fb_project_table()

        client = get_clickhouse_client()

        rows = client.execute("""
            SELECT data
            FROM default.fb_project
        """)

        return [
            json.loads(row[0])
            for row in rows
        ]