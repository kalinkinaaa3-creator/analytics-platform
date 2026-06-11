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


def ensure_fb_project_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_project
        (
            data String
        )
        ENGINE = MergeTree()
        ORDER BY tuple()
    """)