import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import connection

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


class Command(BaseCommand):
    help = "Check freshness and data availability for analytics tables"

    def handle(self, *args, **options):
        logger.info("Table health check started")

        today = date.today()
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