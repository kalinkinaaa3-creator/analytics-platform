import logging
from django.db import connection, transaction

logger = logging.getLogger("external_api.planned_sales")

def rebuild_planned_sales_from_dash_sales_sql():
    logger.info("PlannedSales SQL rebuild started")
    with transaction.atomic():
        with connection.cursor() as cursor:
            logger.info("PlannedSales truncate started")
            cursor.execute("""
                TRUNCATE TABLE planned_sales RESTART IDENTITY
            """)
            logger.info("PlannedSales truncate finished")
            logger.info("PlannedSales insert actual/current months started")
            cursor.execute("""
                INSERT INTO planned_sales
                    (
                        date,
                        level1,
                        level2,
                        level3,
                        fact,
                        appg,
                        appg_slice,
                        id_directory,
                        date_add
                    )
                WITH RECURSIVE months AS (
                    SELECT make_date(EXTRACT(YEAR FROM CURRENT_DATE)::int - 1, 1, 1) AS month_start
                    UNION ALL
                    SELECT (month_start + INTERVAL '1 month')::date
                    FROM months
                    WHERE month_start < date_trunc('month', CURRENT_DATE)::date
                ),
                base AS (
                    SELECT
                        date,
                        date_trunc('month', date)::date AS month_start,
                        partner,
                        contract_initiator,
                        contract_project,
                        SUM(revenue) AS revenue
                    FROM dash_sales
                    WHERE nom <> 'Транспортные услуги'
                      AND date <= CURRENT_DATE
                      AND date >= DATE '2025-01-01'
                    GROUP BY
                        date,
                        date_trunc('month', date)::date,
                        partner,
                        contract_initiator,
                        contract_project
                ),
                mapped AS (
                    SELECT
                        b.date,
                        b.month_start,
                        pd.level1,
                        pd.level2,
                        pd.level3,
                        b.revenue
                    FROM base b
                    LEFT JOIN LATERAL (
                        SELECT
                            p.level1,
                            p.level2,
                            p.level3
                        FROM planned_sales_directory p
                        WHERE (
                            (
                                p.draft3 = b.partner
                                AND p.draft2 =
                                    CASE
                                        WHEN p.level1 = 'СТРАТЕГИ'
                                            AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                        ELSE b.contract_initiator
                                    END
                            )
                            OR (
                                p.level3 = 'Прочие'
                                AND p.draft2 = 'Отдел продаж "Логистика"'
                                AND b.contract_initiator IN (
                                    'Отдел продаж "Логистика"',
                                    'Дирекция по развитию бизнес-проектов'
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM planned_sales_directory pd2
                                    WHERE pd2.draft3 = b.partner
                                    AND pd2.draft2 =
                                        CASE
                                            WHEN pd2.level1 = 'СТРАТЕГИ'
                                                AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                            ELSE b.contract_initiator
                                        END
                                )
                            )
                            OR (
                                p.level3 = 'Прочие'
                                AND p.draft2 = 'Отдел продаж (СПП)'
                                AND b.contract_initiator IN (
                                    'Отдел продаж (СПП)'
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM planned_sales_directory pd2
                                    WHERE pd2.draft3 = b.partner
                                    AND pd2.draft2 =
                                        CASE
                                            WHEN pd2.level1 = 'СТРАТЕГИ'
                                                AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                            ELSE b.contract_initiator
                                        END
                                )
                            )
                            OR (
                                p.draft2 =
                                    CASE
                                        WHEN p.level1 = 'СТРАТЕГИ'
                                            AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                        ELSE b.contract_initiator
                                    END
                                AND p.draft3 = '-'
                                AND b.contract_initiator NOT IN (
                                    'Отдел продаж "Логистика"',
                                    'Отдел продаж (СПП)',
                                    'Дирекция по развитию бизнес-проектов'
                                )
                            )
                        )
                        ORDER BY
                            CASE
                                WHEN p.draft3 = b.partner THEN 1
                                WHEN p.level3 = 'Прочие' THEN 2
                                WHEN p.draft3 = '-' THEN 3
                                ELSE 4
                            END,
                            p.id
                        LIMIT 1
                    ) pd ON TRUE
                    ),
                agg AS (
                    SELECT
                        month_start,
                        level1,
                        level2,
                        level3,
                        SUM(revenue) AS fact
                    FROM mapped
                    GROUP BY month_start, level1, level2, level3
                ),
                appg AS (
                    SELECT
                        (month_start + INTERVAL '1 year')::date AS month_start,
                        level1,
                        level2,
                        level3,
                        SUM(revenue) AS appg
                    FROM mapped
                    GROUP BY month_start, level1, level2, level3
                ),
                appg_slice AS (
                    SELECT
                        (month_start + INTERVAL '1 year')::date AS month_start,
                        level1,
                        level2,
                        level3,
                        SUM(revenue) AS appg_slice
                    FROM mapped
                    WHERE date <= (CURRENT_DATE - INTERVAL '1 year')::date
                    GROUP BY month_start, level1, level2, level3
                ),
                directory_grouped AS (
                    SELECT
                        level1,
                        level2,
                        level3,
                        MAX(id) AS id_directory
                    FROM planned_sales_directory
                    GROUP BY level1, level2, level3
                ),
                full_grid AS (
                    SELECT
                        m.month_start,
                        d.level1,
                        d.level2,
                        d.level3,
                        d.id_directory
                    FROM months m
                    CROSS JOIN directory_grouped d
                )
                SELECT
                    g.month_start AS date,
                    g.level1,
                    g.level2,
                    g.level3,
                    COALESCE(a.fact, 0) AS fact,
                    COALESCE(ap.appg, 0) AS appg,
                    COALESCE(sl.appg_slice, 0) AS appg_slice,
                    g.id_directory,
                    NOW() AS date_add
                FROM full_grid g
                LEFT JOIN agg a
                    ON g.month_start = a.month_start
                    AND g.level1 = a.level1
                    AND g.level2 = a.level2
                    AND g.level3 = a.level3
                LEFT JOIN appg ap
                    ON g.month_start = ap.month_start
                    AND g.level1 = ap.level1
                    AND g.level2 = ap.level2
                    AND g.level3 = ap.level3
                LEFT JOIN appg_slice sl
                    ON g.month_start = sl.month_start
                    AND g.level1 = sl.level1
                    AND g.level2 = sl.level2
                    AND g.level3 = sl.level3
            """)
            actual_inserted = cursor.rowcount
            logger.info(
                "PlannedSales insert actual/current months finished: rows=%s",
                actual_inserted,
            )
            logger.info("PlannedSales insert future months started")
            cursor.execute("""
                INSERT INTO planned_sales
                    (
                        date,
                        level1,
                        level2,
                        level3,
                        fact,
                        appg,
                        appg_slice,
                        id_directory,
                        date_add
                    )
                WITH RECURSIVE months AS (
                    SELECT (date_trunc('month', CURRENT_DATE)::date + INTERVAL '1 month')::date AS month_start
                    UNION ALL
                    SELECT (month_start + INTERVAL '1 month')::date
                    FROM months
                    WHERE month_start < make_date(EXTRACT(YEAR FROM CURRENT_DATE)::int, 12, 1)
                ),
                base AS (
                    SELECT
                        date,
                        date_trunc('month', date)::date AS month_start,
                        partner,
                        contract_initiator,
                        contract_project,
                        SUM(revenue) AS revenue
                    FROM dash_sales
                    WHERE nom <> 'Транспортные услуги'
                      AND date <= CURRENT_DATE
                      AND date >= DATE '2025-01-01'
                    GROUP BY
                        date,
                        date_trunc('month', date)::date,
                        partner,
                        contract_initiator,
                        contract_project
                ),
                mapped AS (
                    SELECT
                        b.date,
                        b.month_start,
                        pd.level1,
                        pd.level2,
                        pd.level3,
                        b.revenue
                    FROM base b
                    LEFT JOIN LATERAL (
                        SELECT
                            p.level1,
                            p.level2,
                            p.level3
                        FROM planned_sales_directory p
                        WHERE (
                            (
                                p.draft3 = b.partner
                                AND p.draft2 =
                                    CASE
                                        WHEN p.level1 = 'СТРАТЕГИ'
                                            AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                        ELSE b.contract_initiator
                                    END
                            )
                            OR (
                                p.level3 = 'Прочие'
                                AND p.draft2 = 'Отдел продаж "Логистика"'
                                AND b.contract_initiator IN (
                                    'Отдел продаж "Логистика"',
                                    'Дирекция по развитию бизнес-проектов'
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM planned_sales_directory pd2
                                    WHERE pd2.draft3 = b.partner
                                    AND pd2.draft2 =
                                        CASE
                                            WHEN pd2.level1 = 'СТРАТЕГИ'
                                                AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                            ELSE b.contract_initiator
                                        END
                                )
                            )
                            OR (
                                p.level3 = 'Прочие'
                                AND p.draft2 = 'Отдел продаж (СПП)'
                                AND b.contract_initiator IN (
                                    'Отдел продаж (СПП)'
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM planned_sales_directory pd2
                                    WHERE pd2.draft3 = b.partner
                                    AND pd2.draft2 =
                                        CASE
                                            WHEN pd2.level1 = 'СТРАТЕГИ'
                                                AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                            ELSE b.contract_initiator
                                        END
                                )
                            )
                            OR (
                                p.draft2 =
                                    CASE
                                        WHEN p.level1 = 'СТРАТЕГИ'
                                            AND b.contract_initiator = 'Коммерческая дирекция'
                                            THEN b.contract_project
                                        ELSE b.contract_initiator
                                    END
                                AND p.draft3 = '-'
                                AND b.contract_initiator NOT IN (
                                    'Отдел продаж "Логистика"',
                                    'Отдел продаж (СПП)',
                                    'Дирекция по развитию бизнес-проектов'
                                )
                            )
                        )
                        ORDER BY
                            CASE
                                WHEN p.draft3 = b.partner THEN 1
                                WHEN p.level3 = 'Прочие' THEN 2
                                WHEN p.draft3 = '-' THEN 3
                                ELSE 4
                            END,
                            p.id
                        LIMIT 1
                    ) pd ON TRUE
                    ),
                appg AS (
                    SELECT
                        (month_start + INTERVAL '1 year')::date AS month_start,
                        level1,
                        level2,
                        level3,
                        SUM(revenue) AS appg
                    FROM mapped
                    GROUP BY month_start, level1, level2, level3
                ),
                directory_grouped AS (
                    SELECT
                        level1,
                        level2,
                        level3,
                        MAX(id) AS id_directory
                    FROM planned_sales_directory
                    GROUP BY level1, level2, level3
                ),
                full_grid AS (
                    SELECT
                        m.month_start,
                        d.level1,
                        d.level2,
                        d.level3,
                        d.id_directory
                    FROM months m
                    CROSS JOIN directory_grouped d
                )
                SELECT
                    g.month_start AS date,
                    g.level1,
                    g.level2,
                    g.level3,
                    NULL AS fact,
                    COALESCE(a.appg, 0) AS appg,
                    NULL AS appg_slice,
                    g.id_directory,
                    NOW() AS date_add
                FROM full_grid g
                LEFT JOIN appg a
                    ON g.month_start = a.month_start
                    AND g.level1 = a.level1
                    AND g.level2 = a.level2
                    AND g.level3 = a.level3
            """)
            future_inserted = cursor.rowcount
            logger.info(
                "PlannedSales insert future months finished: rows=%s",
                future_inserted,
            )
    result = {
        "planned_sales_actual_rows": actual_inserted,
        "planned_sales_future_rows": future_inserted,
        "planned_sales_total_rows": actual_inserted + future_inserted,
    }
    logger.info("PlannedSales SQL rebuild finished: %s", result)
    return result