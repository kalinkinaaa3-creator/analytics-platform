from datasets.models import YdWordstatFor
from uuid import uuid4
import logging

from analytics.clickhouse.repository import YD_WORDSTAT_COLUMNS
from analytics.clickhouse.client import get_clickhouse_client
from analytics.clickhouse.schema import ensure_yd_wordstat_for_table

logger = logging.getLogger("external_api.yd_wordstat")


def sync_yd_wordstat_to_clickhouse() -> int:
    rows = list(
        YdWordstatFor.objects.all()
        .order_by("id")
        .values()
    )

    if not rows:
        raise ValueError("Refusing to replace Wordstat history with an empty table")
    ensure_yd_wordstat_for_table()
    client = get_clickhouse_client()
    staging = f"default.yd_wordstat_for_stage_{uuid4().hex}"
    created = False
    try:
        engine = client.execute("SELECT engine FROM system.databases WHERE name = 'default'")[0][0]
        if engine not in ("Atomic", "Shared"):
            raise RuntimeError("Wordstat publication requires an Atomic/Shared ClickHouse database")
        client.execute(f"CREATE TABLE {staging} AS default.yd_wordstat_for")
        created = True
        columns = ", ".join(YD_WORDSTAT_COLUMNS)
        for offset in range(0, len(rows), 10000):
            client.execute(f"INSERT INTO {staging} ({columns}) VALUES", [
                tuple(row.get(column) for column in YD_WORDSTAT_COLUMNS)
                for row in rows[offset:offset + 10000]])
        if client.execute(f"SELECT count() FROM {staging}")[0][0] != len(rows):
            raise RuntimeError("Wordstat staging row count does not match PostgreSQL")
        client.execute(f"EXCHANGE TABLES default.yd_wordstat_for AND {staging}")
        return len(rows)
    finally:
        try:
            if created:
                client.execute(f"DROP TABLE IF EXISTS {staging}")
        except Exception:
            logger.exception("Could not remove Wordstat statistics staging table %s", staging)
        finally:
            client.disconnect()
