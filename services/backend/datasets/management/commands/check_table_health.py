import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import connection

from context_analytics.services.refresh import DEFAULT_INCREMENTAL_DAYS
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


def check_seo_analytics_health(cursor, today, problems, ok):
    """Validate the watermark-based SEO refresh and all prepared report pages."""
    name = "SEO analytics (seo_analytics_daily)"
    local_problems = []
    required_pages = (
        "visits",
        "new-visitors",
        "returning-visitors",
        "search-phrases",
        "traffic-change",
        "conversions",
        "unique-conversions",
        "landing-pages",
    )
    completed_through = today - timedelta(days=1)
    first_current_month = completed_through.replace(day=1)
    previous_month_last = first_current_month - timedelta(days=1)
    expected_date_from = previous_month_last.replace(day=1)
    expected_date_to = completed_through

    run_table = "seo_refresh_run"
    request_log_table = "seo_api_request_log"

    if not table_exists(cursor, run_table):
        local_problems.append(f"{name}: таблица {run_table} не существует")
    else:
        cursor.execute(
            f'''
            SELECT id, status,
                   (started_at AT TIME ZONE 'Europe/Moscow')::date,
                   (finished_at AT TIME ZONE 'Europe/Moscow')::date,
                   stats,
                   COALESCE(error, ''),
                   started_at,
                   finished_at
            FROM "{run_table}"
            WHERE trigger = %s
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            ''',
            ["scheduled"],
        )
        latest_run = cursor.fetchone()
        if latest_run is None:
            local_problems.append(f"{name}: отсутствуют плановые запуски")
        else:
            (
                run_id,
                status,
                started_date,
                finished_date,
                stats,
                error_text,
                started_at,
                finished_at,
            ) = latest_run
            if started_date != today:
                local_problems.append(
                    f"{name}: последний плановый запуск={started_date}, нужно={today}"
                )
            if status != "success":
                suffix = f", error={error_text}" if error_text else ""
                local_problems.append(
                    f"{name}: последний плановый запуск #{run_id}, status={status}{suffix}"
                )
            elif finished_date != today:
                local_problems.append(
                    f"{name}: запуск #{run_id} завершён={finished_date}, нужно={today}"
                )

            completed_pages = {
                page
                for page, result in (stats or {}).get("pages", {}).items()
                if result == "success"
            }
            missing_run_pages = sorted(set(required_pages) - completed_pages)
            if missing_run_pages:
                local_problems.append(
                    f"{name}: запуск #{run_id} не подтвердил страницы: "
                    + ", ".join(missing_run_pages)
                )

            if table_exists(cursor, request_log_table):
                failed_requests = scalar(
                    cursor,
                    f'''
                    SELECT COUNT(*)
                    FROM "{request_log_table}"
                    WHERE created_at >= %s
                      AND created_at <= COALESCE(%s, CURRENT_TIMESTAMP)
                      AND success = FALSE
                    ''',
                    [started_at, finished_at],
                )
                if failed_requests:
                    local_problems.append(
                        f"{name}: неуспешных запросов API в запуске #{run_id} — "
                        f"{failed_requests}"
                    )
            else:
                local_problems.append(
                    f"{name}: таблица {request_log_table} не существует"
                )

    goal_table = "seo_goal"
    if not table_exists(cursor, goal_table):
        local_problems.append(f"{name}: таблица {goal_table} не существует")
    else:
        available_goals = scalar(
            cursor,
            f'SELECT COUNT(*) FROM "{goal_table}" WHERE is_available = TRUE',
        )
        goals_updated = scalar(
            cursor,
            f'''SELECT MAX((source_updated_at AT TIME ZONE 'Europe/Moscow')::date)
                FROM "{goal_table}" WHERE is_available = TRUE''',
        )
        if not available_goals:
            local_problems.append(f"{name}: каталог целей Метрики пуст")
        if goals_updated != today:
            local_problems.append(
                f"{name}: каталог целей обновлён={goals_updated}, нужно={today}"
            )

    try:
        from analytics.clickhouse.client import get_clickhouse_client

        clickhouse = get_clickhouse_client()
        required_tables = (
            "default.seo_traffic_monthly",
            "default.seo_phrase_monthly",
            "default.seo_conversion_monthly",
            "default.seo_landing_monthly",
        )
        expected_months = (
            expected_date_from,
            expected_date_to.replace(day=1),
        )
        for table in required_tables:
            exists_rows = clickhouse.execute(f"EXISTS TABLE {table}")
            if not exists_rows or not exists_rows[0][0]:
                local_problems.append(f"{name}: таблица ClickHouse {table} не существует")
                continue
            month_rows = clickhouse.execute(
                f"""SELECT month, count(), max(toDate(loaded_at))
                    FROM {table} WHERE month IN %(months)s
                    GROUP BY month ORDER BY month""",
                {"months": expected_months},
            )
            by_month = {month: (count, loaded) for month, count, loaded in month_rows}
            for month in expected_months:
                count, loaded = by_month.get(month, (0, None))
                if count <= 0:
                    local_problems.append(f"{name}: {table} не содержит строк за {month:%Y-%m}")
                if loaded != today:
                    local_problems.append(
                        f"{name}: {table} за {month:%Y-%m} обновлена={loaded}, нужно={today}"
                    )
    except Exception as exc:
        local_problems.append(
            f"{name}: не удалось проверить ClickHouse-витрину: {exc}"
        )

    logger.info(
        "%s: expected_window=%s..%s required_pages=%s problems=%s",
        name,
        expected_date_from,
        expected_date_to,
        required_pages,
        local_problems,
    )
    if local_problems:
        problems.extend(local_problems)
    else:
        ok.append(name)


def check_context_analytics_health(cursor, today, problems, ok):
    """Validate the 06:50 Direct/Metрика refresh and its ClickHouse facts."""
    name = "Context analytics (context_analytics_daily)"
    local_problems = []
    yesterday = today - timedelta(days=1)
    window_start = yesterday - timedelta(days=DEFAULT_INCREMENTAL_DAYS - 1)
    run_table = "context_refresh_run"
    request_log_table = "context_api_request_log"
    campaign_table = "context_campaign"

    if not table_exists(cursor, run_table):
        local_problems.append(f"{name}: таблица {run_table} не существует")
        latest_run = None
    else:
        cursor.execute(
            f'''
            SELECT id, status,
                   (started_at AT TIME ZONE 'Europe/Moscow')::date,
                   (finished_at AT TIME ZONE 'Europe/Moscow')::date,
                   stats, COALESCE(error, ''), started_at, finished_at
            FROM "{run_table}"
            WHERE trigger = %s
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            ''',
            ["scheduled"],
        )
        latest_run = cursor.fetchone()
        if latest_run is None:
            local_problems.append(f"{name}: отсутствуют плановые запуски")
        else:
            run_id, status, started_date, finished_date, stats, error_text, started_at, finished_at = latest_run
            if started_date != today:
                local_problems.append(f"{name}: последний плановый запуск={started_date}, нужно={today}")
            if status != "success":
                suffix = f", error={error_text}" if error_text else ""
                local_problems.append(f"{name}: запуск #{run_id}, status={status}{suffix}")
            elif finished_date != today:
                local_problems.append(f"{name}: запуск #{run_id} завершён={finished_date}, нужно={today}")
            expected_stats = ("performance_rows", "criteria_rows", "visitor_rows")
            for key in expected_stats:
                if int((stats or {}).get(key) or 0) <= 0:
                    local_problems.append(f"{name}: запуск #{run_id}, {key}={(stats or {}).get(key)}")
            initial_backfill = bool((stats or {}).get("initial_backfill"))
            expected_run_start = max(
                date(2024, 1, 1),
                date(today.year - 3, today.month, 1),
            ).isoformat() if initial_backfill else window_start.isoformat()
            actual_run_start = (stats or {}).get("date_from")
            invalid_start = actual_run_start != expected_run_start if initial_backfill else (
                not actual_run_start or actual_run_start > expected_run_start
            )
            if invalid_start or (stats or {}).get("date_to") != yesterday.isoformat():
                local_problems.append(
                    f"{name}: запуск #{run_id} обновил окно {(stats or {}).get('date_from')}.."
                    f"{(stats or {}).get('date_to')}, начало должно быть не позднее {expected_run_start}, "
                    f"конец={yesterday}"
                )
            if not table_exists(cursor, request_log_table):
                local_problems.append(f"{name}: таблица {request_log_table} не существует")
            else:
                failed = scalar(
                    cursor,
                    f'''SELECT COUNT(*) FROM "{request_log_table}"
                        WHERE created_at >= %s
                          AND created_at <= COALESCE(%s, CURRENT_TIMESTAMP)
                          AND success = FALSE''',
                    [started_at, finished_at],
                )
                if failed:
                    local_problems.append(f"{name}: неуспешных Direct-запросов в запуске #{run_id} — {failed}")

    if not table_exists(cursor, campaign_table):
        local_problems.append(f"{name}: таблица {campaign_table} не существует")
    else:
        available = scalar(cursor, f'SELECT COUNT(*) FROM "{campaign_table}" WHERE is_available = TRUE')
        updated = scalar(
            cursor,
            f'''SELECT MAX((source_updated_at AT TIME ZONE 'Europe/Moscow')::date)
                FROM "{campaign_table}" WHERE is_available = TRUE''',
        )
        if not available:
            local_problems.append(f"{name}: каталог кампаний пуст")
        if updated != today:
            local_problems.append(f"{name}: каталог кампаний обновлён={updated}, нужно={today}")

    try:
        from analytics.clickhouse.client import get_clickhouse_client

        clickhouse = get_clickhouse_client()
        tables = {
            "default.context_performance_daily": True,
            "default.context_performance_goal_daily": False,
            "default.context_criteria_daily": True,
            "default.context_criteria_goal_daily": False,
            "default.context_visitor_daily": True,
        }
        available_tables = set()
        for table, must_have_yesterday in tables.items():
            exists = clickhouse.execute(f"EXISTS TABLE {table}")
            if not exists or not exists[0][0]:
                local_problems.append(f"{name}: таблица ClickHouse {table} не существует")
                continue
            available_tables.add(table)
            count, max_date, loaded = clickhouse.execute(
                f"""SELECT count(), max(date), max(toDate(loaded_at)) FROM {table}
                    WHERE date BETWEEN %(date_from)s AND %(date_to)s""",
                {"date_from": window_start, "date_to": yesterday},
            )[0]
            if count <= 0:
                # Goal facts may legitimately be empty when none of the selected
                # goals was reached in the refresh window.
                if must_have_yesterday:
                    local_problems.append(f"{name}: {table} не содержит строк за {window_start}..{yesterday}")
                continue
            if must_have_yesterday and max_date != yesterday:
                local_problems.append(f"{name}: {table} содержит данные по {max_date}, нужно по {yesterday}")
            if loaded != today:
                local_problems.append(f"{name}: {table} обновлена={loaded}, нужно={today}")

        if "default.context_performance_daily" in available_tables:
            total = clickhouse.execute(
                """SELECT sum(impressions), sum(clicks), toFloat64(sum(cost)), sum(sessions)
                   FROM default.context_performance_daily WHERE date = %(date)s""",
                {"date": yesterday},
            )[0]
            by_dimensions = clickhouse.execute(
                """SELECT sum(impressions), sum(clicks), toFloat64(sum(cost)), sum(sessions)
                   FROM (
                     SELECT device, gender, age, sum(impressions) impressions, sum(clicks) clicks,
                            sum(cost) cost, sum(sessions) sessions
                     FROM default.context_performance_daily WHERE date = %(date)s
                     GROUP BY device, gender, age
                   )""",
                {"date": yesterday},
            )[0]
            differences = [abs(float(left or 0) - float(right or 0)) for left, right in zip(total, by_dimensions)]
            if differences[0] or differences[1] or differences[3] or differences[2] > 0.1:
                local_problems.append(f"{name}: нарушена сверка общего и демографического среза, разницы={differences}")
    except Exception as exc:
        local_problems.append(f"{name}: не удалось проверить ClickHouse-витрины: {exc}")

    logger.info("%s: expected_window=%s..%s problems=%s", name, window_start, yesterday, local_problems)
    if local_problems:
        problems.extend(local_problems)
    else:
        ok.append(name)


def check_lead_generation_mart_health(today, problems, ok):
    """Validate completeness and internal consistency of the weekly mart."""
    name = "Lead generation weekly mart"
    table = "default.lead_generation_weekly_mart"
    local_problems = []

    try:
        from analytics.clickhouse.client import get_clickhouse_client

        clickhouse = get_clickhouse_client()
        exists = clickhouse.execute(f"EXISTS TABLE {table}")
        if not exists or not exists[0][0]:
            local_problems.append(f"{name}: таблица ClickHouse {table} не существует")
        else:
            count, total_weeks, source_rows, built_date = clickhouse.execute(
                f"""SELECT count(), countIf(row_kind = 'total'),
                           countIf(row_kind = 'source'), max(toDate(mart_built_at))
                    FROM {table}"""
            )[0]
            if count <= 0:
                local_problems.append(f"{name}: таблица {table} пуста")
            else:
                if total_weeks <= 0:
                    local_problems.append(f"{name}: отсутствуют недельные итоговые строки")
                if source_rows <= 0:
                    local_problems.append(f"{name}: отсутствуют строки по источникам")
                if built_date != today:
                    local_problems.append(
                        f"{name}: витрина опубликована={built_date}, нужно={today}"
                    )

                invalid_rows = clickhouse.execute(
                    f"""SELECT count() FROM {table}
                        WHERE row_kind NOT IN ('total', 'source')
                           OR toDayOfWeek(week_start) != 1
                           OR (row_kind = 'total' AND source_id != '')
                           OR (row_kind = 'source' AND source_id = '')"""
                )[0][0]
                if invalid_rows:
                    local_problems.append(
                        f"{name}: строк с некорректным типом, ключом или началом недели — {invalid_rows}"
                    )

                duplicates = clickhouse.execute(
                    f"""SELECT count() FROM (
                            SELECT row_kind, week_start, source_id, count() amount
                            FROM {table}
                            GROUP BY row_kind, week_start, source_id
                            HAVING amount > 1
                        )"""
                )[0][0]
                if duplicates:
                    local_problems.append(f"{name}: дублей составного ключа — {duplicates}")

                week_set_differences = clickhouse.execute(
                    f"""WITH expected AS (
                            SELECT DISTINCT week_start FROM (
                                SELECT toStartOfWeek(source_created_at, 1) week_start
                                FROM default.bitrix_lead_analytics
                                WHERE source_created_at IS NOT NULL
                                UNION ALL
                                SELECT toStartOfWeek(date, 1) week_start
                                FROM default.context_performance_daily
                            )
                        ), actual AS (
                            SELECT week_start FROM {table} WHERE row_kind = 'total'
                        )
                        SELECT
                            (SELECT count() FROM expected
                             WHERE week_start NOT IN (SELECT week_start FROM actual)),
                            (SELECT count() FROM actual
                             WHERE week_start NOT IN (SELECT week_start FROM expected))"""
                )[0]
                if any(week_set_differences):
                    local_problems.append(
                        f"{name}: неполный набор недель, отсутствует={week_set_differences[0]}, "
                        f"лишних={week_set_differences[1]}"
                    )

                source_mismatches = clickhouse.execute(
                    f"""SELECT count() FROM (
                            SELECT totals.week_start
                            FROM (
                                SELECT week_start, total_leads, target_leads,
                                       additional_apm_leads, non_target_leads,
                                       unprocessed_leads, lead_opportunity
                                FROM {table} WHERE row_kind = 'total'
                            ) totals
                            LEFT JOIN (
                                SELECT week_start, sum(total_leads) total_leads,
                                       sum(target_leads) target_leads,
                                       sum(additional_apm_leads) additional_apm_leads,
                                       sum(non_target_leads) non_target_leads,
                                       sum(unprocessed_leads) unprocessed_leads,
                                       sum(lead_opportunity) lead_opportunity
                                FROM {table} WHERE row_kind = 'source'
                                GROUP BY week_start
                            ) sources USING week_start
                            WHERE totals.total_leads != ifNull(sources.total_leads, 0)
                               OR totals.target_leads != ifNull(sources.target_leads, 0)
                               OR totals.additional_apm_leads != ifNull(sources.additional_apm_leads, 0)
                               OR totals.non_target_leads != ifNull(sources.non_target_leads, 0)
                               OR totals.unprocessed_leads != ifNull(sources.unprocessed_leads, 0)
                               OR totals.lead_opportunity != ifNull(sources.lead_opportunity, 0)
                        )"""
                )[0][0]
                if source_mismatches:
                    local_problems.append(
                        f"{name}: недель, где итог не совпадает с суммой источников — {source_mismatches}"
                    )

                raw_mismatches = clickhouse.execute(
                    f"""SELECT count() FROM (
                            SELECT mart.week_start
                            FROM (
                                SELECT week_start, total_leads, target_leads,
                                       additional_apm_leads, non_target_leads,
                                       unprocessed_leads, lead_opportunity, direct_cost
                                FROM {table} WHERE row_kind = 'total'
                            ) mart
                            LEFT JOIN (
                                SELECT toStartOfWeek(source_created_at, 1) week_start,
                                       count() total_leads,
                                       countIf(dashboard_status = 'target') target_leads,
                                       countIf(is_apm = 1 AND dashboard_status != 'target') additional_apm_leads,
                                       countIf(status_semantic_id = 'F' AND is_apm = 0) non_target_leads,
                                       countIf(status_semantic_id = 'P') unprocessed_leads,
                                       sum(ifNull(opportunity, 0)) lead_opportunity
                                FROM default.bitrix_lead_analytics
                                WHERE source_created_at IS NOT NULL
                                GROUP BY week_start
                            ) bitrix USING week_start
                            LEFT JOIN (
                                SELECT toStartOfWeek(date, 1) week_start, sum(cost) direct_cost
                                FROM default.context_performance_daily GROUP BY week_start
                            ) direct USING week_start
                            WHERE mart.total_leads != ifNull(bitrix.total_leads, 0)
                               OR mart.target_leads != ifNull(bitrix.target_leads, 0)
                               OR mart.additional_apm_leads != ifNull(bitrix.additional_apm_leads, 0)
                               OR mart.non_target_leads != ifNull(bitrix.non_target_leads, 0)
                               OR mart.unprocessed_leads != ifNull(bitrix.unprocessed_leads, 0)
                               OR mart.lead_opportunity != ifNull(bitrix.lead_opportunity, 0)
                               OR mart.direct_cost != ifNull(direct.direct_cost, 0)
                        )"""
                )[0][0]
                if raw_mismatches:
                    local_problems.append(
                        f"{name}: недель с расхождением относительно исходных таблиц — {raw_mismatches}"
                    )
    except Exception as exc:
        local_problems.append(f"{name}: не удалось проверить ClickHouse-витрину: {exc}")

    logger.info("%s: problems=%s", name, local_problems)
    if local_problems:
        problems.extend(local_problems)
    else:
        ok.append(name)


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

            try:
                from analytics.services.wordstat_health import inspect_wordstat
                wordstat = inspect_wordstat(today=today)
                if wordstat["ok"]:
                    ok.append("Wordstat")
                else:
                    problems.extend(f"Wordstat: {problem}" for problem in wordstat["problems"])
                logger.info("Wordstat health: %s", wordstat)
            except Exception as exc:
                logger.exception("Wordstat health check failed")
                problems.append(f"Wordstat: проверка не выполнена: {exc}")

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
            check_seo_analytics_health(
                cursor,
                today,
                problems,
                ok,
            )
            check_context_analytics_health(
                cursor,
                today,
                problems,
                ok,
            )
            check_lead_generation_mart_health(
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
