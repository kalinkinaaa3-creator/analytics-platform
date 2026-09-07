import logging
from uuid import uuid4

from django.core.cache import cache

from analytics.clickhouse.client import get_clickhouse_client
from bitrix24.services.clickhouse import TABLE_NAME as BITRIX_TABLE
from context_analytics.services.clickhouse import PERFORMANCE_TABLE
from dashboards.realtime import notify_dashboard_updated

from .cache import invalidate_lead_generation_cache


MART_TABLE = "default.lead_generation_weekly_mart"
LOCK_KEY = "leadgen:mart:lock"
PENDING_KEY = "leadgen:mart:pending"
LOCK_TIMEOUT = 30 * 60
logger = logging.getLogger("lead_generation.clickhouse")


class MartAlreadyRunning(RuntimeError):
    pass


def _create_table(client, table_name):
    client.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name}
        (
            row_kind LowCardinality(String),
            week_start Date,
            source_id String,
            source_name String,
            direct_cost Decimal64(2),
            total_leads UInt64,
            target_leads UInt64,
            additional_apm_leads UInt64,
            non_target_leads UInt64,
            unprocessed_leads UInt64,
            lead_opportunity Decimal64(2),
            bitrix_loaded_at Nullable(DateTime64(3, 'Europe/Moscow')),
            context_loaded_at Nullable(DateTime64(3, 'Europe/Moscow')),
            mart_built_at DateTime64(3, 'Europe/Moscow')
        )
        ENGINE = MergeTree()
        PARTITION BY toYear(week_start)
        ORDER BY (row_kind, week_start, source_id)
    """)


def ensure_mart_table():
    client = get_clickhouse_client()
    _create_table(client, MART_TABLE)
    return client


def rebuild_mart():
    """Build the complete mart off-line and expose it with one atomic swap."""
    if not cache.add(LOCK_KEY, "running", timeout=LOCK_TIMEOUT):
        raise MartAlreadyRunning("Витрина лидогенерации уже обновляется.")
    from analytics.services.bitrix_notify import send_bitrix_message
    client = None
    staging = f"default.lead_generation_weekly_mart_staging_{uuid4().hex[:12]}"
    try:
        client = get_clickhouse_client()
        built_at = client.execute("SELECT now64(3, 'Europe/Moscow')")[0][0]
        _create_table(client, MART_TABLE)
        _create_table(client, staging)
        client.execute(f"""
            INSERT INTO {staging}
            SELECT
                'total', weeks.week_start, '', '',
                toDecimal64(ifNull(direct.direct_cost, 0), 2),
                toUInt64(ifNull(bitrix.total_leads, 0)),
                toUInt64(ifNull(bitrix.target_leads, 0)),
                toUInt64(ifNull(bitrix.additional_apm_leads, 0)),
                toUInt64(ifNull(bitrix.non_target_leads, 0)),
                toUInt64(ifNull(bitrix.unprocessed_leads, 0)),
                toDecimal64(ifNull(bitrix.lead_opportunity, 0), 2),
                bitrix.bitrix_loaded_at, direct.context_loaded_at,
                %(built_at)s
            FROM
            (
                SELECT DISTINCT week_start FROM
                (
                    SELECT DISTINCT toStartOfWeek(source_created_at, 1) AS week_start
                    FROM {BITRIX_TABLE}
                    WHERE source_created_at IS NOT NULL
                    UNION ALL
                    SELECT DISTINCT toStartOfWeek(date, 1) AS week_start
                    FROM {PERFORMANCE_TABLE}
                )
            ) weeks
            LEFT JOIN
            (
                SELECT
                    toStartOfWeek(source_created_at, 1) AS week_start,
                    count() AS total_leads,
                    countIf(dashboard_status = 'target') AS target_leads,
                    countIf(is_apm = 1 AND dashboard_status != 'target') AS additional_apm_leads,
                    countIf(status_semantic_id = 'F' AND is_apm = 0) AS non_target_leads,
                    countIf(status_semantic_id = 'P') AS unprocessed_leads,
                    sum(ifNull(opportunity, 0)) AS lead_opportunity,
                    toNullable(max(calculated_at)) AS bitrix_loaded_at
                FROM {BITRIX_TABLE}
                WHERE source_created_at IS NOT NULL
                GROUP BY week_start
            ) bitrix USING week_start
            LEFT JOIN
            (
                SELECT toStartOfWeek(date, 1) AS week_start,
                       sum(cost) AS direct_cost,
                       toNullable(max(loaded_at)) AS context_loaded_at
                FROM {PERFORMANCE_TABLE}
                GROUP BY week_start
            ) direct USING week_start
            UNION ALL
            SELECT
                'source', toStartOfWeek(source_created_at, 1) AS week_start,
                if(source_id = '', '__unknown__', source_id) AS normalized_source_id,
                any(if(source_name != '', source_name,
                       if(source_id = '', 'Источник не указан', source_id))),
                toDecimal64(0, 2), toUInt64(count()),
                toUInt64(countIf(dashboard_status = 'target')),
                toUInt64(countIf(is_apm = 1 AND dashboard_status != 'target')),
                toUInt64(countIf(status_semantic_id = 'F' AND is_apm = 0)),
                toUInt64(countIf(status_semantic_id = 'P')),
                toDecimal64(sum(ifNull(opportunity, 0)), 2),
                toNullable(max(calculated_at)),
                CAST(NULL AS Nullable(DateTime64(3, 'Europe/Moscow'))),
                %(built_at)s
            FROM {BITRIX_TABLE}
            WHERE source_created_at IS NOT NULL
            GROUP BY week_start, normalized_source_id
        """, {"built_at": built_at})

        duplicates = client.execute(f"""
            SELECT count() FROM
            (
                SELECT row_kind, week_start, source_id, count() AS amount
                FROM {staging}
                GROUP BY row_kind, week_start, source_id
                HAVING amount > 1
            )
        """)[0][0]
        if duplicates:
            raise RuntimeError(f"В staging-витрине обнаружены дубли ключей: {duplicates}.")

        mismatches = client.execute(f"""
            SELECT count() FROM
            (
                SELECT totals.week_start
                FROM
                (
                    SELECT week_start, total_leads, target_leads,
                           additional_apm_leads, non_target_leads,
                           unprocessed_leads, lead_opportunity
                    FROM {staging}
                    WHERE row_kind = 'total'
                ) totals
                LEFT JOIN
                (
                    SELECT week_start, sum(total_leads) AS total_leads,
                           sum(target_leads) AS target_leads,
                           sum(additional_apm_leads) AS additional_apm_leads,
                           sum(non_target_leads) AS non_target_leads,
                           sum(unprocessed_leads) AS unprocessed_leads,
                           sum(lead_opportunity) AS lead_opportunity
                    FROM {staging} WHERE row_kind = 'source'
                    GROUP BY week_start
                ) sources USING week_start
                WHERE totals.total_leads != ifNull(sources.total_leads, 0)
                   OR totals.target_leads != ifNull(sources.target_leads, 0)
                   OR totals.additional_apm_leads != ifNull(sources.additional_apm_leads, 0)
                   OR totals.non_target_leads != ifNull(sources.non_target_leads, 0)
                   OR totals.unprocessed_leads != ifNull(sources.unprocessed_leads, 0)
                   OR totals.lead_opportunity != ifNull(sources.lead_opportunity, 0)
            )
        """)[0][0]
        if mismatches:
            raise RuntimeError(f"Недельные итоги не совпали с суммой источников: {mismatches}.")

        client.execute(f"EXCHANGE TABLES {MART_TABLE} AND {staging}")
        client.execute(f"DROP TABLE {staging}")
        invalidate_lead_generation_cache()
        try:
            notify_dashboard_updated(
                "LeadGeneration",
                change_type="mart_published",
                updated_at=built_at.isoformat(),
            )
        except Exception:
            logger.exception("Lead generation mart was published, but WebSocket notification failed")
        return int(client.execute(f"SELECT count() FROM {MART_TABLE}")[0][0])
    except BaseException as exc:
        exc._bitrix_notification_attempted = True
        send_bitrix_message("[b]Лидогенерация[/b] Ошибка обновления витрины ClickHouse. Подробности в логе lead_generation.", logger_name="lead_generation")
        if client is not None:
            try:
                client.execute(f"DROP TABLE IF EXISTS {staging}")
            except Exception:
                logger.exception("Could not remove failed lead generation staging table")
        raise
    finally:
        cache.delete(LOCK_KEY)


def rebuild_mart_safely():
    result = None
    for _attempt in range(3):
        try:
            result = rebuild_mart()
        except MartAlreadyRunning:
            cache.set(PENDING_KEY, True, timeout=LOCK_TIMEOUT)
            return None
        except Exception:
            logger.exception("Failed to rebuild lead generation mart")
            return None
        if not cache.get(PENDING_KEY):
            return result
        cache.delete(PENDING_KEY)
    logger.warning("Lead generation mart still has pending refresh requests after three rebuilds")
    return result
