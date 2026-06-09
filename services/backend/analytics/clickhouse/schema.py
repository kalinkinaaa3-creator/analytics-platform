from analytics.clickhouse.client import get_clickhouse_client


def ensure_dataset_rows_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.dataset_rows
        (
            dataset_id UInt64,
            data String
        )
        ENGINE = MergeTree()
        ORDER BY dataset_id
    """)