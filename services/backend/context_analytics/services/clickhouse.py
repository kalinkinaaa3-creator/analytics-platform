from contextlib import contextmanager
import logging
from uuid import uuid4

from analytics.clickhouse.client import get_clickhouse_client


PERFORMANCE_TABLE = "default.context_performance_daily"
GOAL_TABLE = "default.context_performance_goal_daily"
CRITERIA_TABLE = "default.context_criteria_daily"
CRITERIA_GOAL_TABLE = "default.context_criteria_goal_daily"
VISITOR_TABLE = "default.context_visitor_daily"
_tables_ready = False
logger = logging.getLogger("context_analytics.clickhouse")
LIVE_TABLES = (PERFORMANCE_TABLE, GOAL_TABLE, CRITERIA_TABLE, CRITERIA_GOAL_TABLE, VISITOR_TABLE)

DDL = (
    f"""CREATE TABLE IF NOT EXISTS {PERFORMANCE_TABLE} (
      date Date, campaign_id UInt64, campaign_name String, campaign_type LowCardinality(String),
      ad_group_id UInt64, ad_group_name String, ad_network_type LowCardinality(String), device LowCardinality(String),
      gender LowCardinality(String), age LowCardinality(String), impressions UInt64, clicks UInt64,
      cost Decimal64(2), sessions Nullable(UInt64), bounces Nullable(UInt64), avg_pageviews Float64,
      avg_impression_position Nullable(Float64), avg_click_position Nullable(Float64),
      loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE=MergeTree PARTITION BY toYYYYMM(date)
      ORDER BY (date,campaign_id,ad_group_id,ad_network_type,device,gender,age)""",
    f"""CREATE TABLE IF NOT EXISTS {GOAL_TABLE} (
      date Date, campaign_id UInt64, ad_group_id UInt64, device LowCardinality(String),
      gender LowCardinality(String), age LowCardinality(String), goal_id UInt64,
      goal_name String, conversions UInt64, loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE=MergeTree PARTITION BY toYYYYMM(date)
      ORDER BY (date,goal_id,campaign_id,ad_group_id,device,gender,age)""",
    f"""CREATE TABLE IF NOT EXISTS {CRITERIA_TABLE} (
      date Date, campaign_id UInt64, campaign_name String, campaign_type LowCardinality(String),
      ad_group_id UInt64, ad_group_name String, ad_network_type LowCardinality(String), criterion_id UInt64, criterion String,
      criterion_type LowCardinality(String), impressions UInt64, clicks UInt64, cost Decimal64(2),
      sessions Nullable(UInt64), bounces Nullable(UInt64), avg_pageviews Float64,
      avg_impression_position Nullable(Float64), avg_click_position Nullable(Float64),
      loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE=MergeTree PARTITION BY toYYYYMM(date)
      ORDER BY (date,campaign_id,ad_group_id,ad_network_type,criterion_type,criterion_id)""",
    f"""CREATE TABLE IF NOT EXISTS {CRITERIA_GOAL_TABLE} (
      date Date, campaign_id UInt64, ad_group_id UInt64, criterion_id UInt64,
      criterion_type LowCardinality(String), goal_id UInt64, goal_name String,
      conversions UInt64, loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE=MergeTree PARTITION BY toYYYYMM(date)
      ORDER BY (date,goal_id,campaign_id,ad_group_id,criterion_type,criterion_id)""",
    f"""CREATE TABLE IF NOT EXISTS {VISITOR_TABLE} (
      date Date, campaign_id UInt64, users UInt64, new_users UInt64,
      loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE=MergeTree PARTITION BY toYYYYMM(date)
      ORDER BY (date,campaign_id)""",
)


def _migrate_visitor_table(client):
    """Collapse the legacy demographic visitor fact to date/campaign grain."""
    columns = {
        row[0] for row in client.execute(
            "SELECT name FROM system.columns WHERE database='default' AND table='context_visitor_daily'"
        )
    }
    if not {"device", "gender", "age"}.intersection(columns):
        return

    suffix = uuid4().hex
    replacement = f"{VISITOR_TABLE}__schema_{suffix}"
    backup = f"{VISITOR_TABLE}__legacy_{suffix}"
    try:
        client.execute(f"""CREATE TABLE {replacement} (
          date Date, campaign_id UInt64, users UInt64, new_users UInt64,
          loaded_at DateTime64(3, 'Europe/Moscow')
        ) ENGINE=MergeTree PARTITION BY toYYYYMM(date)
          ORDER BY (date,campaign_id)""")
        client.execute(f"""INSERT INTO {replacement}
          SELECT date,campaign_id,sum(users),sum(new_users),max(loaded_at)
          FROM {VISITOR_TABLE} GROUP BY date,campaign_id""")
        client.execute(f"RENAME TABLE {VISITOR_TABLE} TO {backup}, {replacement} TO {VISITOR_TABLE}")
        client.execute(f"DROP TABLE {backup}")
    except Exception:
        client.execute(f"DROP TABLE IF EXISTS {replacement}")
        raise


def _migrate_optional_performance_metrics(client):
    """Keep Direct's unavailable marker distinct from a real numeric zero."""
    prefixes = ("context_performance_daily", "context_criteria_daily")
    tables = [
        row[0] for row in client.execute(
            "SELECT name FROM system.tables WHERE database='default'"
        )
        if row[0].startswith(prefixes)
    ]
    target_types = {
        "sessions": "Nullable(UInt64)",
        "bounces": "Nullable(UInt64)",
        "avg_impression_position": "Nullable(Float64)",
        "avg_click_position": "Nullable(Float64)",
    }
    for table in tables:
        current = dict(client.execute(
            "SELECT name,type FROM system.columns WHERE database='default' AND table=%(table)s",
            {"table": table},
        ))
        for column, target_type in target_types.items():
            if column in current and current[column] != target_type:
                client.execute(f"ALTER TABLE default.{table} MODIFY COLUMN {column} {target_type}")
        if "ad_network_type" not in current:
            client.execute(
                f"ALTER TABLE default.{table} ADD COLUMN ad_network_type "
                "LowCardinality(String) DEFAULT 'Не определено' AFTER ad_group_name"
            )


def ensure_tables():
    global _tables_ready
    client = get_clickhouse_client()
    if not _tables_ready:
        for ddl in DDL:
            client.execute(ddl)
        _migrate_optional_performance_metrics(client)
        _migrate_visitor_table(client)
        _tables_ready = True
    return client


def context_warehouse_is_empty():
    client = ensure_tables()
    return int(client.execute(f"SELECT count() FROM {PERFORMANCE_TABLE}")[0][0]) == 0


def context_warehouse_max_date():
    """Return the loading watermark from the primary performance table."""
    client = ensure_tables()
    # max(Date) returns the Date epoch for an empty ClickHouse table. Keep the
    # empty state explicit so the command reliably selects initial backfill.
    return client.execute(f"SELECT maxOrNull(date) FROM {PERFORMANCE_TABLE}")[0][0]


def _validate_staged_tables(tables):
    if set(tables) != set(LIVE_TABLES):
        raise ValueError("Некорректный набор staging-таблиц контекстной аналитики.")
    for live, staged in tables.items():
        prefix = f"{live}__refresh_"
        suffix = staged.removeprefix(prefix)
        if not staged.startswith(prefix) or not suffix.isalnum():
            raise ValueError("Некорректное имя staging-таблицы контекстной аналитики.")
    return tables


def create_staged_tables():
    client = ensure_tables()
    suffix = uuid4().hex
    tables = {table: f"{table}__refresh_{suffix}" for table in LIVE_TABLES}
    try:
        for table in LIVE_TABLES:
            client.execute(f"CREATE TABLE {tables[table]} AS {table}")
            client.execute(f"INSERT INTO {tables[table]} SELECT * FROM {table}")
    except Exception:
        for staged in tables.values():
            client.execute(f"DROP TABLE IF EXISTS {staged}")
        raise
    return client, tables


def staged_tables_exist(tables):
    try:
        tables = _validate_staged_tables(tables)
    except (TypeError, ValueError):
        return False
    client = ensure_tables()
    existing = {
        f"{database}.{table}"
        for database, table in client.execute(
            "SELECT database,name FROM system.tables WHERE database = 'default'"
        )
    }
    return all(staged in existing for staged in tables.values())


def discard_staged_tables(tables):
    tables = _validate_staged_tables(tables)
    client = ensure_tables()
    for staged in tables.values():
        client.execute(f"DROP TABLE IF EXISTS {staged}")


def publish_staged_tables(tables):
    tables = _validate_staged_tables(tables)
    client = ensure_tables()
    suffix = uuid4().hex
    backups = {table: f"{table}__backup_{suffix}" for table in LIVE_TABLES}
    renames = []
    for table in LIVE_TABLES:
        renames += [f"{table} TO {backups[table]}", f"{tables[table]} TO {table}"]
    client.execute(f"RENAME TABLE {', '.join(renames)}")
    for backup in backups.values():
        try:
            client.execute(f"DROP TABLE {backup}")
        except Exception:
            # Publication already succeeded atomically; a leftover backup is
            # safer than reporting the refresh as failed and rebuilding it.
            logger.exception("Failed to drop published context backup %s", backup)


@contextmanager
def staged_tables():
    client, shadows = create_staged_tables()
    try:
        yield client, shadows
        publish_staged_tables(shadows)
    except Exception:
        discard_staged_tables(shadows)
        raise


def replace_range(client, table, date_from, date_to, rows, columns):
    client.execute(f"ALTER TABLE {table} DELETE WHERE date BETWEEN %(date_from)s AND %(date_to)s SETTINGS mutations_sync=1",
                   {"date_from": date_from, "date_to": date_to})
    if rows:
        client.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES", rows)
