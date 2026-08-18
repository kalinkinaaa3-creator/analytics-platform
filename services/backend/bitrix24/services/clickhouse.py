from __future__ import annotations

from uuid import uuid4

from analytics.clickhouse.client import get_clickhouse_client

from bitrix24.models import BitrixLeadAnalytics


TABLE_NAME = "default.bitrix_lead_analytics"
COLUMNS = (
    "lead_id",
    "title",
    "source_created_at",
    "source_updated_at",
    "opportunity",
    "source_id",
    "source_name",
    "status_id",
    "status_name",
    "dashboard_status",
    "manager_id",
    "manager_name",
    "primary_department_id",
    "department_name",
    "is_apm",
    "is_low_quality",
    "is_unmapped",
    "is_processed",
    "is_final",
    "first_processing_at",
    "processing_duration_seconds",
    "processing_duration_days",
    "processing_state",
    "calculated_at",
)


def _create_table(client, table_name: str) -> None:
    client.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name}
        (
            lead_id Int64,
            title String,
            source_created_at Nullable(DateTime64(3, 'Europe/Moscow')),
            source_updated_at Nullable(DateTime64(3, 'Europe/Moscow')),
            opportunity Nullable(Decimal(18, 2)),
            source_id String,
            source_name String,
            status_id String,
            status_name String,
            dashboard_status LowCardinality(String),
            manager_id Nullable(Int64),
            manager_name String,
            primary_department_id Nullable(Int64),
            department_name String,
            is_apm UInt8,
            is_low_quality UInt8,
            is_unmapped UInt8,
            is_processed UInt8,
            is_final UInt8,
            first_processing_at Nullable(DateTime64(3, 'Europe/Moscow')),
            processing_duration_seconds Nullable(Int64),
            processing_duration_days Nullable(Decimal(20, 8)),
            processing_state LowCardinality(String),
            calculated_at DateTime64(3, 'Europe/Moscow')
        )
        ENGINE = MergeTree()
        ORDER BY lead_id
        """
    )


def _ensure_display_columns(client, table_name: str) -> None:
    for definition in (
        "title String AFTER lead_id",
        "source_updated_at Nullable(DateTime64(3, 'Europe/Moscow')) AFTER source_created_at",
        "opportunity Nullable(Decimal(18, 2)) AFTER source_updated_at",
    ):
        client.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {definition}")


def _row(item: BitrixLeadAnalytics) -> tuple:
    return (
        item.lead_id,
        item.title,
        item.source_created_at,
        item.source_updated_at,
        item.opportunity,
        item.source_id,
        item.source_name,
        item.status_id,
        item.status_name,
        item.dashboard_status,
        item.manager_id,
        item.manager_name,
        item.primary_department_id,
        item.department_name,
        int(item.is_apm),
        int(item.is_low_quality),
        int(item.is_unmapped),
        int(item.is_processed),
        int(item.is_final),
        item.first_processing_at,
        item.processing_duration_seconds,
        item.processing_duration_days,
        item.processing_state,
        item.calculated_at,
    )


def sync_lead_analytics_to_clickhouse(*, chunk_size: int = 1000) -> int:
    client = get_clickhouse_client()
    staging_name = f"default.bitrix_lead_analytics_staging_{uuid4().hex[:12]}"
    _create_table(client, TABLE_NAME)
    _ensure_display_columns(client, TABLE_NAME)
    _create_table(client, staging_name)
    inserted = 0
    batch = []
    insert_sql = f"INSERT INTO {staging_name} ({', '.join(COLUMNS)}) VALUES"
    try:
        queryset = BitrixLeadAnalytics.objects.all().order_by("lead_id")
        for item in queryset.iterator(chunk_size=chunk_size):
            batch.append(_row(item))
            if len(batch) >= chunk_size:
                client.execute(insert_sql, batch)
                inserted += len(batch)
                batch = []
        if batch:
            client.execute(insert_sql, batch)
            inserted += len(batch)

        client.execute(f"EXCHANGE TABLES {TABLE_NAME} AND {staging_name}")
        client.execute(f"DROP TABLE {staging_name}")
        from bitrix24.cache import invalidate_bitrix24_cache

        invalidate_bitrix24_cache()
        return inserted
    except BaseException:
        client.execute(f"DROP TABLE IF EXISTS {staging_name}")
        raise
