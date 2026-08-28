import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from analytics.services.bitrix_notify import send_bitrix_message


logger = logging.getLogger("maintenance.table_health")


TABLE_CHECKS = [
    {
        "name": "Projects",
        "table": "fb_project",
        "date_add_column": "date_add",
        "fresh_days": 0,
    },
    {
        "name": "DashSales staging",
        "table": "dash_sales",
        "date_add_column": "date_add",
        "data_date_column": "date",
        "fresh_days": 0,
    },
    {
        "name": "PlannedSales",
        "table": "planned_sales",
        "date_add_column": "date_add",
        "data_date_column": None,
        "fresh_days": 0,
    },
    {
        "name": "Revenue",
        "table": "revenue_sales",
        "date_add_column": "date_add",
        "data_date_column": "date",
        "fresh_days": 0,
    },
    {
        "name": "Purchases raw",
        "table": "fb_purchases_raw",
        "date_add_column": "date_add",
        "data_date_column": "date_1C",
        "fresh_days": 0,
    },
    {
        "name": "Purchases",
        "table": "fb_purchases_use",
        "date_add_column": "date_add",
        "data_date_column": "date_draft",
        "fresh_days": 0,
    },
    {
        "name": "Turnover raw",
        "table": "fb_turnover_raw",
        "date_add_column": "date_add",
        "data_date_column": "date_stock",
        "fresh_days": 0,
    },
    {
        "name": "Turnover",
        "table": "fb_turnover_use",
        "date_add_column": "date_add",
        "data_date_column": "date_stock",
        "fresh_days": 0,
    },
    {
        "name": "Accreceiv raw",
        "table": "fb_accreceiv_raw",
        "date_add_column": "date_add",
        "data_date_column": "date_start",
        "fresh_days": 0,
    },
    {
        "name": "Accreceiv",
        "table": "fb_accreceiv_use",
        "date_add_column": "date_add",
        "data_date_column": "date_start",
        "fresh_days": 0,
    },
    {
        "name": "Wordstat",
        "table": "yd_wordstat_for",
        "date_add_column": None,
        "data_date_column": None,
        "fresh_days": None,
    },
    {
        "name": "Nomenclature",
        "table": "nomenclature",
        "date_add_column": "date_add",
        "data_date_column": None,
        "fresh_days": 7,
    },
    {
        "name": "Nomenclature price",
        "table": "nomenclature_price",
        "date_add_column": "date_add",
        "data_date_column": "date",
        "fresh_days": 0,
    },
    
]


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT to_regclass(%s)
        """,
        [table_name],
    )

    return cursor.fetchone()[0] is not None


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s
              AND column_name = %s
        )
        """,
        [table_name, column_name],
    )

    return cursor.fetchone()[0]


def scalar(cursor, sql, params=None):
    cursor.execute(sql, params or [])
    row = cursor.fetchone()
    return row[0] if row else None


def check_base_parser_health(cursor, today, problems, ok):
    name = "Base parser"
    table = "parser_product_url"

    if not table_exists(cursor, table):
        problems.append(f"{name}: таблица {table} не существует")
        return

    total = scalar(
        cursor,
        f'SELECT COUNT(*) FROM "{table}" WHERE source = %s',
        ["base"],
    )
    if not total:
        problems.append(f"{name}: отсутствуют строки source=base")
        return

    active = scalar(
        cursor,
        f'''SELECT COUNT(*) FROM "{table}"
            WHERE source = %s AND status = %s''',
        ["base", "active"],
    )
    if not active:
        problems.append(f"{name}: отсутствуют активные base-товары")

    max_date_update = scalar(
        cursor,
        f'''SELECT MAX((date_update AT TIME ZONE 'Europe/Moscow')::date)
            FROM "{table}" WHERE source = %s''',
        ["base"],
    )
    if max_date_update != today:
        problems.append(
            f"{name}: date_update устарел. max={max_date_update}, нужно={today}"
        )

    active_unloaded = scalar(
        cursor,
        f'''SELECT COUNT(*) FROM "{table}"
            WHERE source = %s AND status = %s AND is_loaded = FALSE''',
        ["base", "active"],
    )
    if active_unloaded:
        problems.append(
            f"{name}: активных незагруженных товаров — {active_unloaded}"
        )

    unexpected_condition = """
        source = %s
        AND status = %s
        AND (
            last_error IS NULL
            OR BTRIM(last_error) = ''
            OR last_error NOT IN (%s)
        )
    """
    unexpected_params = ["base", "inactive", "missing_from_map"]
    unexpected_inactive = scalar(
        cursor,
        f'SELECT COUNT(*) FROM "{table}" WHERE {unexpected_condition}',
        unexpected_params,
    )
    if unexpected_inactive:
        problems.append(
            f"{name}: неожиданных неактивных товаров — {unexpected_inactive}"
        )

    if active_unloaded or unexpected_inactive:
        cursor.execute(
            f'''
            SELECT id, status, is_loaded, COALESCE(last_error, ''), url
            FROM "{table}"
            WHERE (
                source = %s AND status = %s AND is_loaded = FALSE
            ) OR ({unexpected_condition})
            ORDER BY id
            LIMIT 10
            ''',
            ["base", "active", *unexpected_params],
        )
        for product_key, status, is_loaded, last_error, url in cursor.fetchall():
            problems.append(
                f"{name}: product_key={product_key}, status={status}, "
                f"is_loaded={is_loaded}, error={last_error or 'NULL'}, url={url}"
            )

    if (
        active
        and max_date_update == today
        and not active_unloaded
        and not unexpected_inactive
    ):
        ok.append(name)

    logger.info(
        "%s: total=%s active=%s max_date_update=%s active_unloaded=%s "
        "unexpected_inactive=%s",
        name,
        total,
        active,
        max_date_update,
        active_unloaded,
        unexpected_inactive,
    )


def check_bitrix24_health(cursor, today, problems, ok):
    """Check Bitrix24 downloads, allowing an empty weekend activity window."""
    refresh_name = "Bitrix24 CRM refresh (bitrix24_crm_refresh_12h)"
    reconciliation_name = (
        "Bitrix24 recent leads reconciliation "
        "(bitrix24_recent_leads_reconciliation_weekly)"
    )
    local_problems = []
    # The 08:04 check validates the preceding overnight activity window.
    # Saturday/Sunday inactivity is therefore visible on Sunday/Monday.
    requires_received_leads = today.weekday() not in (0, 6)
    lead_last_seen_date = None

    for table in ("bitrix24_lead", "bitrix24_lead_analytics"):
        if not table_exists(cursor, table):
            local_problems.append(f"{refresh_name}: таблица {table} не существует")
            continue
        row_count = scalar(cursor, f'SELECT COUNT(*) FROM "{table}"')
        if not row_count:
            local_problems.append(f"{refresh_name}: таблица {table} пуста")
        elif table == "bitrix24_lead":
            lead_last_seen_date = scalar(
                cursor,
                f'''
                SELECT MAX(
                    (last_seen_at AT TIME ZONE 'Europe/Moscow')::date
                )
                FROM "{table}"
                ''',
            )

    if requires_received_leads and lead_last_seen_date != today:
        local_problems.append(
            f"{refresh_name}: не получены ожидаемые строки leads, "
            f"max(last_seen_at)={lead_last_seen_date}, нужно={today}"
        )

    state_table = "bitrix24_sync_state"
    if not table_exists(cursor, state_table):
        local_problems.append(
            f"{refresh_name}: таблица {state_table} не существует"
        )
    else:
        required_entities = (
            "departments",
            "users",
            "crm_dictionary",
            "crm_fields_1",
            "leads",
            "stage_history_1",
        )
        cursor.execute(
            f'''
            SELECT entity, status,
                   (last_success_at AT TIME ZONE 'Europe/Moscow')::date,
                   rows_received,
                   COALESCE(error_text, '')
            FROM "{state_table}"
            WHERE entity IN %s
            ''',
            [required_entities],
        )
        states = {
            entity: (status, last_success_date, rows_received, error_text)
            for (
                entity,
                status,
                last_success_date,
                rows_received,
                error_text,
            ) in cursor.fetchall()
        }
        # The regular DAG runs Monday-Saturday. At the Sunday 08:04 health
        # check, Saturday's successful refresh is therefore the expected one.
        min_success_date = (
            today - timedelta(days=1)
            if today.weekday() == 6
            else today
        )
        for entity in required_entities:
            state = states.get(entity)
            if state is None:
                local_problems.append(
                    f"{refresh_name}: отсутствует состояние entity={entity}"
                )
                continue
            status, last_success_date, rows_received, error_text = state
            if status != "success":
                suffix = f", error={error_text}" if error_text else ""
                local_problems.append(
                    f"{refresh_name}: entity={entity}, status={status}{suffix}"
                )
            if last_success_date is None or last_success_date < min_success_date:
                local_problems.append(
                    f"{refresh_name}: entity={entity}, последнее успешное "
                    f"обновление={last_success_date}, нужно >= {min_success_date}"
                )
            if entity == "leads" and requires_received_leads and not rows_received:
                local_problems.append(
                    f"{refresh_name}: entity=leads получил "
                    f"rows_received={rows_received}, ожидалось > 0"
                )

        logger.info(
            "%s: expected_entities=%s min_success_date=%s states=%s",
            refresh_name,
            required_entities,
            min_success_date,
            states,
        )
        logger.info(
            "%s: requires_received_leads=%s lead_last_seen_date=%s",
            refresh_name,
            requires_received_leads,
            lead_last_seen_date,
        )

    run_table = "bitrix24_sync_run"
    if not table_exists(cursor, run_table):
        local_problems.append(
            f"{reconciliation_name}: таблица {run_table} не существует"
        )
    else:
        cursor.execute(
            f'''
            SELECT status,
                   (finished_at AT TIME ZONE 'Europe/Moscow')::date,
                   rows_received,
                   rows_deactivated,
                   COALESCE(error_text, '')
            FROM "{run_table}"
            WHERE entity = %s AND mode = %s
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            ''',
            ["leads", "repair"],
        )
        latest_repair = cursor.fetchone()
        min_repair_date = today - timedelta(days=7)
        if latest_repair is None:
            local_problems.append(
                f"{reconciliation_name}: отсутствуют repair-запуски leads"
            )
        else:
            status, finished_date, received, deactivated, error_text = latest_repair
            if status != "success":
                suffix = f", error={error_text}" if error_text else ""
                local_problems.append(
                    f"{reconciliation_name}: последний запуск status={status}{suffix}"
                )
            if finished_date is None or finished_date < min_repair_date:
                local_problems.append(
                    f"{reconciliation_name}: последнее завершение="
                    f"{finished_date}, нужно >= {min_repair_date}"
                )
            logger.info(
                "%s: status=%s finished_date=%s received=%s deactivated=%s",
                reconciliation_name,
                status,
                finished_date,
                received,
                deactivated,
            )

    if local_problems:
        problems.extend(local_problems)
    else:
        ok.extend((refresh_name, reconciliation_name))


class Command(BaseCommand):
    help = "Check freshness and data availability for analytics tables"

    def handle(self, *args, **options):
        logger.info("Table health check started")

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        period_start = today - timedelta(days=3)

        problems = []
        ok = []

        with connection.cursor() as cursor:
            for check in TABLE_CHECKS:
                name = check["name"]
                table = check["table"]
                date_add_column = check.get("date_add_column")
                data_date_column = check.get("data_date_column")
                fresh_days = check.get("fresh_days")

                logger.info("Checking table: %s (%s)", name, table)

                if not table_exists(cursor, table):
                    problems.append(f"{name}: таблица {table} не существует")
                    logger.warning("%s: table does not exist", table)
                    continue

                total_count = scalar(
                    cursor,
                    f'SELECT COUNT(*) FROM "{table}"',
                )

                if total_count == 0:
                    problems.append(f"{name}: таблица {table} пуста")
                    logger.warning("%s: empty table", table)
                    continue

                if date_add_column:
                    if not column_exists(cursor, table, date_add_column):
                        problems.append(f"{name}: нет колонки {date_add_column}")
                        logger.warning("%s: missing column %s", table, date_add_column)
                    else:
                        max_date_add = scalar(
                            cursor,
                            f'''
                            SELECT MAX(
                                ("{date_add_column}" AT TIME ZONE 'Europe/Moscow')::date
                            )
                            FROM "{table}"
                            ''',
                        )

                        min_allowed = today - timedelta(days=fresh_days)

                        if max_date_add is None or max_date_add < min_allowed:
                            problems.append(
                                f"{name}: date_add устарел. max={max_date_add}, нужно >= {min_allowed}"
                            )
                            logger.warning(
                                "%s: stale date_add. max=%s, min_allowed=%s",
                                table,
                                max_date_add,
                                min_allowed,
                            )

                if data_date_column:
                    if not column_exists(cursor, table, data_date_column):
                        problems.append(f"{name}: нет колонки {data_date_column}")
                        logger.warning("%s: missing column %s", table, data_date_column)
                    else:
                        max_data_date = scalar(
                            cursor,
                            f'SELECT MAX("{data_date_column}") FROM "{table}"',
                        )

                        count_recent = scalar(
                            cursor,
                            f'''
                            SELECT COUNT(*)
                            FROM "{table}"
                            WHERE "{data_date_column}" >= %s
                              AND "{data_date_column}" <= %s
                            ''',
                            [period_start, yesterday],
                        )

                        logger.info(
                            "%s: max_data_date=%s, recent_count=%s",
                            table,
                            max_data_date,
                            count_recent,
                        )

                        if count_recent <= 0:
                            problems.append(
                                f"{name}: нет данных за период {period_start} — {yesterday}"
                            )

                ok.append(name)

            check_base_parser_health(
                cursor,
                today,
                problems,
                ok,
            )
            check_bitrix24_health(
                cursor,
                today,
                problems,
                ok,
            )

        if problems:
            message = (
                "[b]table_health.py[/b]\n"
                "Внимание! Есть проблемы с обновлением таблиц:\n"
                + "\n".join(f"- {problem}" for problem in problems)
            )

            logger.warning(message)
            send_bitrix_message(
                message,
                logger_name="maintenance.table_health",
            )

            self.stdout.write(message)

        else:
            message = (
                "[b]table_health.py[/b]\n"
                "Проверка завершена: по настроенным таблицам критичных проблем не найдено."
            )

            logger.info(message)
            send_bitrix_message(
                message,
                logger_name="maintenance.table_health",
            )

            self.stdout.write(message)
