from uuid import uuid4
from contextlib import contextmanager
import logging

from analytics.clickhouse.client import get_clickhouse_client


TRAFFIC_TABLE = "default.seo_traffic_monthly"
PHRASE_TABLE = "default.seo_phrase_monthly"
CONVERSION_TABLE = "default.seo_conversion_monthly"
LANDING_TABLE = "default.seo_landing_monthly"
_tables_ready = False
logger = logging.getLogger("seo_analytics.clickhouse")
SEO_LIVE_TABLES = (TRAFFIC_TABLE, PHRASE_TABLE, CONVERSION_TABLE, LANDING_TABLE)


DDL = (
    f"""
    CREATE TABLE IF NOT EXISTS {TRAFFIC_TABLE}
    (
        month Date, device LowCardinality(String), search_engine LowCardinality(String),
        region String, robotness LowCardinality(String),
        age_interval LowCardinality(String), gender LowCardinality(String),
        visits UInt64, pageviews UInt64, users UInt64, new_users UInt64,
        new_visits UInt64, new_pageviews UInt64,
        returned_visits UInt64, returned_pageviews UInt64,
        loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE = MergeTree PARTITION BY toYYYYMM(month)
    ORDER BY (month, device, search_engine, robotness, age_interval, gender, region)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {PHRASE_TABLE}
    (
        month Date, search_engine LowCardinality(String), robotness LowCardinality(String),
        search_phrase String, phrase_type LowCardinality(String), visits UInt64,
        pageviews UInt64, users UInt64, new_users UInt64,
        loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE = MergeTree PARTITION BY toYYYYMM(month)
    ORDER BY (month, phrase_type, search_engine, robotness, search_phrase)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {CONVERSION_TABLE}
    (
        month Date, device LowCardinality(String), search_engine LowCardinality(String),
        region String, search_phrase String, phrase_type LowCardinality(String),
        age_interval LowCardinality(String), gender LowCardinality(String),
        goal_id UInt64, goal_name String, goal_reaches UInt64, goal_users UInt64,
        visits UInt64, users UInt64, loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE = MergeTree PARTITION BY toYYYYMM(month)
    ORDER BY (month, goal_id, phrase_type, device, search_engine, region, age_interval, gender, search_phrase)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {LANDING_TABLE}
    (
        month Date, device LowCardinality(String), search_engine LowCardinality(String),
        region String, landing_url String, visits UInt64, pageviews UInt64,
        users UInt64, new_users UInt64, loaded_at DateTime64(3, 'Europe/Moscow')
    ) ENGINE = MergeTree PARTITION BY toYYYYMM(month)
    ORDER BY (month, device, search_engine, region, landing_url)
    """,
)


def ensure_seo_tables():
    global _tables_ready
    client = get_clickhouse_client()
    if _tables_ready:
        return client
    for statement in DDL:
        client.execute(statement)
    for name, after in (
        ("new_visits", "new_users"),
        ("new_pageviews", "new_visits"),
        ("returned_visits", "new_pageviews"),
        ("returned_pageviews", "returned_visits"),
    ):
        client.execute(
            f"ALTER TABLE {TRAFFIC_TABLE} ADD COLUMN IF NOT EXISTS {name} UInt64 AFTER {after}"
        )
    client.execute(
        f"ALTER TABLE {PHRASE_TABLE} ADD COLUMN IF NOT EXISTS pageviews UInt64 AFTER visits"
    )
    client.execute(
        f"ALTER TABLE {LANDING_TABLE} DROP COLUMN IF EXISTS page_title"
    )
    client.execute(
        f"ALTER TABLE {CONVERSION_TABLE} ADD COLUMN IF NOT EXISTS age_interval LowCardinality(String) AFTER phrase_type"
    )
    client.execute(
        f"ALTER TABLE {CONVERSION_TABLE} ADD COLUMN IF NOT EXISTS gender LowCardinality(String) AFTER age_interval"
    )
    _tables_ready = True
    return client


def drop_legacy_report_mart():
    get_clickhouse_client().execute("DROP TABLE IF EXISTS default.seo_report_mart")


def replace_month(table, month, rows, columns):
    client = ensure_seo_tables()
    client.execute(
        f"ALTER TABLE {table} DELETE WHERE month = %(month)s SETTINGS mutations_sync = 1",
        {"month": month},
    )
    if rows:
        client.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES", rows)


def _validate_seo_staged_tables(tables):
    if set(tables) != set(SEO_LIVE_TABLES):
        raise ValueError("Некорректный набор staging-таблиц SEO-аналитики.")
    for live, staged in tables.items():
        prefix = f"{live}__refresh_"
        suffix = staged.removeprefix(prefix)
        if not staged.startswith(prefix) or not suffix.isalnum():
            raise ValueError("Некорректное имя staging-таблицы SEO-аналитики.")
    return tables


def create_seo_staged_tables():
    client = ensure_seo_tables()
    suffix = uuid4().hex
    shadows = {table: f"{table}__refresh_{suffix}" for table in SEO_LIVE_TABLES}
    try:
        for table, shadow in shadows.items():
            client.execute(f"CREATE TABLE {shadow} AS {table}")
            client.execute(f"INSERT INTO {shadow} SELECT * FROM {table}")
    except Exception:
        for shadow in shadows.values():
            client.execute(f"DROP TABLE IF EXISTS {shadow}")
        raise
    return shadows


def seo_staged_tables_exist(tables):
    try:
        tables = _validate_seo_staged_tables(tables)
    except (TypeError, ValueError):
        return False
    client = ensure_seo_tables()
    existing = {
        f"{database}.{table}"
        for database, table in client.execute(
            "SELECT database,name FROM system.tables WHERE database = 'default'"
        )
    }
    return all(staged in existing for staged in tables.values())


def discard_seo_staged_tables(tables):
    tables = _validate_seo_staged_tables(tables)
    client = ensure_seo_tables()
    for staged in tables.values():
        client.execute(f"DROP TABLE IF EXISTS {staged}")


def publish_seo_staged_tables(tables):
    tables = _validate_seo_staged_tables(tables)
    client = ensure_seo_tables()
    suffix = uuid4().hex
    backups = {table: f"{table}__backup_{suffix}" for table in SEO_LIVE_TABLES}
    renames = []
    for table in SEO_LIVE_TABLES:
        renames.extend((f"{table} TO {backups[table]}", f"{tables[table]} TO {table}"))
    client.execute(f"RENAME TABLE {', '.join(renames)}")
    for backup in backups.values():
        try:
            client.execute(f"DROP TABLE {backup}")
        except Exception:
            logger.exception("Failed to drop published SEO backup %s", backup)


@contextmanager
def staged_seo_tables():
    """Build a full refresh in ClickHouse and expose it only after success."""
    shadows = create_seo_staged_tables()
    try:
        yield shadows
        publish_seo_staged_tables(shadows)
    except Exception:
        discard_seo_staged_tables(shadows)
        raise


def reclassify_phrase_types(masks):
    client = ensure_seo_tables()
    normalized = [str(mask).strip().lower().replace("ё", "е") for mask in masks if str(mask).strip()]
    brand_conditions = [
        f"positionCaseInsensitiveUTF8(replaceAll(search_phrase, 'ё', 'е'), %(mask_{index})s) > 0"
        for index, _mask in enumerate(normalized)
    ]
    params = {f"mask_{index}": mask for index, mask in enumerate(normalized)}
    brand = " OR ".join(brand_conditions) or "0"
    expression = (
        "multiIf(empty(trimBoth(search_phrase)) OR lowerUTF8(search_phrase) IN "
        "('не определено', 'not defined', 'undefined'), 'Не определено', "
        f"({brand}), 'Брендовые', 'Небрендовые')"
    )
    table_columns = {
        PHRASE_TABLE: (
            "month, search_engine, robotness, search_phrase, phrase_type, "
            "visits, pageviews, users, new_users, loaded_at"
        ),
        CONVERSION_TABLE: (
            "month, device, search_engine, region, search_phrase, phrase_type, "
            "age_interval, gender, "
            "goal_id, goal_name, goal_reaches, goal_users, visits, users, loaded_at"
        ),
    }
    for table, columns in table_columns.items():
        suffix = uuid4().hex
        shadow = f"{table}__reclass_{suffix}"
        backup = f"{table}__backup_{suffix}"
        select_columns = columns.replace("phrase_type", f"{expression} AS phrase_type")
        try:
            client.execute(f"CREATE TABLE {shadow} AS {table}")
            client.execute(
                f"INSERT INTO {shadow} ({columns}) SELECT {select_columns} FROM {table}",
                params,
            )
            client.execute(f"RENAME TABLE {table} TO {backup}, {shadow} TO {table}")
            client.execute(f"DROP TABLE {backup}")
        except Exception:
            client.execute(f"DROP TABLE IF EXISTS {shadow}")
            raise


def seo_warehouse_is_empty():
    client = ensure_seo_tables()
    return any(
        not int(client.execute(f"SELECT count() FROM {table}")[0][0])
        for table in (TRAFFIC_TABLE, PHRASE_TABLE, CONVERSION_TABLE, LANDING_TABLE)
    )


def traffic_audience_needs_backfill():
    """Old traffic rows have no segmented visits/pageviews for audience depth."""
    client = ensure_seo_tables()
    return bool(client.execute(
        f"SELECT 1 FROM {TRAFFIC_TABLE} "
        "WHERE visits > 0 AND new_visits + returned_visits = 0 LIMIT 1"
    ))


def seo_warehouse_max_month():
    """Return the loading watermark from the primary SEO traffic table."""
    client = ensure_seo_tables()
    # ClickHouse returns the Date epoch (1970-01-01) for max(Date) over an
    # empty table. maxOrNull is required so the refresh can distinguish an
    # empty warehouse from a real loading watermark.
    return client.execute(f"SELECT maxOrNull(month) FROM {TRAFFIC_TABLE}")[0][0]
