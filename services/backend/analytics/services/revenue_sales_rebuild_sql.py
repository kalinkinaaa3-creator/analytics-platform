# /opt/analytics-platform/services/backend/analytics/services/revenue_sales_rebuild_sql.py

import logging
from datetime import date, timedelta

from django.db import connection, transaction
from django.db.models import Max

from datasets.models import DashSales, RevenueSales


logger = logging.getLogger("analytics.revenue_sales")


def get_revenue_sales_rebuild_start_date(end_date: date | None = None):
    end_date = end_date or date.today()

    revenue_exists = RevenueSales.objects.exists()

    if not revenue_exists:
        logger.info("RevenueSales full rebuild period: RevenueSales is empty")
        return None

    max_date = DashSales.objects.aggregate(
        max_date=Max("date"),
    )["max_date"]

    logger.info("RevenueSales DashSales current max date: %s", max_date)

    if max_date is None:
        logger.info("RevenueSales full rebuild period: DashSales is empty")
        return None

    if end_date.isoweekday() == 6:
        logger.info("RevenueSales Saturday rebuild period: 300 days")
        return max_date - timedelta(days=300)

    logger.info("RevenueSales regular rebuild period: 150 days")
    return max_date - timedelta(days=150)


def rebuild_revenue_sales_from_dash_sales_sql(
    start_date: date | None = None,
    end_date: date | None = None,
):
    if start_date is None:
        start_date = get_revenue_sales_rebuild_start_date(end_date=end_date)

    logger.info(
        "RevenueSales SQL rebuild started: start_date=%s, end_date=%s",
        start_date,
        end_date,
    )

    with transaction.atomic():
        with connection.cursor() as cursor:
            if start_date is None:
                logger.info("RevenueSales truncate started")

                cursor.execute("""
                    TRUNCATE TABLE revenue_sales RESTART IDENTITY
                """)

                deleted = None

                logger.info("RevenueSales truncate finished")
            else:
                logger.info(
                    "RevenueSales delete started: date >= %s",
                    start_date,
                )

                cursor.execute(
                    """
                    DELETE FROM revenue_sales
                    WHERE date >= %s
                    """,
                    [start_date],
                )

                deleted = cursor.rowcount

                logger.info("RevenueSales deleted rows: %s", deleted)

            logger.info("RevenueSales insert started")

            cursor.execute(
                """
                INSERT INTO revenue_sales
                    (
                        date,
                        direction,
                        project,
                        manager,
                        partner,
                        partner_code,
                        consignee,
                        nom_view,
                        nom_category,
                        nom_group,
                        nom,
                        nom_code,
                        type_doc,
                        quantity,
                        weight_total,
                        revenue,
                        is_new_sku,
                        is_new_client,
                        date_add
                    )

                WITH base_all AS (
                    SELECT
                        ds.date,
                        ds.partner,
                        ds.partner_code,
                        ds.contract_initiator,
                        ds.contract_project,
                        ds.contract_fullname AS manager,

                        CASE
                            WHEN ds.consignee IS NULL
                              OR TRIM(ds.consignee) = ''
                              OR TRIM(ds.consignee) = '-'
                                THEN ds.partner
                            ELSE ds.consignee
                        END AS consignee,

                        ds.nom_view,
                        ds.nom_category,
                        ds.nom_group,
                        ds.nom,
                        ds.nom_code,
                        ds.type_doc,
                        COALESCE(ds.quantity, 0) AS quantity,
                        COALESCE(ds.weight_total, 0) AS weight_total,
                        COALESCE(ds.revenue, 0) AS revenue
                    FROM dash_sales ds
                    WHERE ds.date IS NOT NULL
                ),

                base AS (
                    SELECT *
                    FROM base_all
                    WHERE (%s IS NULL OR date >= %s)
                ),

                mapped AS (
                    SELECT
                        b.*,

                        CASE
                            WHEN b.nom = 'Транспортные услуги'
                                THEN 'Прочие'
                            WHEN pd.level1 = 'СТРАТЕГИ'
                                THEN pd.level1
                            WHEN pd.level2 IS NOT NULL
                                THEN pd.level2
                            ELSE 'Прочие'
                        END AS direction,

                        CASE
                            WHEN b.nom = 'Транспортные услуги'
                                THEN 'Прочие'
                            WHEN pd.level1 = 'СТРАТЕГИ'
                                THEN pd.level2
                            WHEN pd.level3 IS NOT NULL
                                THEN pd.level3
                            ELSE 'Прочие'
                        END AS project

                    FROM base b

                    LEFT JOIN LATERAL (
                        SELECT
                            p.level1,
                            p.level2,
                            p.level3
                        FROM planned_sales_directory p
                        WHERE
                            b.nom <> 'Транспортные услуги'
                            AND (
                                (
                                    p.draft3 = b.partner
                                    AND p.draft2 =
                                        CASE
                                            WHEN p.level1 = 'СТРАТЕГИ'
                                                THEN b.contract_project
                                            ELSE b.contract_initiator
                                        END
                                )

                                OR (
                                    p.level3 = 'Прочие'
                                    AND p.draft2 = 'Отдел продаж "Логистика"'
                                    AND b.contract_initiator = 'Отдел продаж "Логистика"'
                                    AND b.partner NOT IN ('РВБ ООО', 'ИНТЕРНЕТ РЕШЕНИЯ ООО')
                                )

                                OR (
                                    p.level3 = 'Прочие'
                                    AND p.draft2 = 'Отдел продаж (СПП)'
                                    AND b.contract_initiator = 'Отдел продаж (СПП)'
                                    AND b.partner NOT IN ('РВБ ООО', 'ИНТЕРНЕТ РЕШЕНИЯ ООО')
                                )

                                OR (
                                    p.draft2 =
                                        CASE
                                            WHEN p.level1 = 'СТРАТЕГИ'
                                                THEN b.contract_project
                                            ELSE b.contract_initiator
                                        END
                                    AND p.draft3 = '-'
                                    AND b.contract_initiator NOT IN (
                                        'Отдел продаж "Логистика"',
                                        'Отдел продаж (СПП)'
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

                first_sku AS (
                    SELECT
                        nom_code,
                        MIN(date) AS first_date
                    FROM base_all
                    WHERE nom_code IS NOT NULL
                    GROUP BY nom_code
                ),

                first_client AS (
                    SELECT
                        partner_code,
                        MIN(date) AS first_date
                    FROM base_all
                    WHERE partner_code IS NOT NULL
                    GROUP BY partner_code
                )

                SELECT
                    m.date,
                    m.direction,
                    m.project,
                    m.manager,
                    m.partner,
                    m.partner_code,
                    m.consignee,
                    m.nom_view,
                    m.nom_category,
                    m.nom_group,
                    m.nom,
                    m.nom_code,
                    m.type_doc,
                    m.quantity,
                    m.weight_total,
                    m.revenue,

                    CASE
                        WHEN m.nom_code IS NOT NULL
                         AND m.date = fs.first_date
                            THEN TRUE
                        ELSE FALSE
                    END AS is_new_sku,

                    CASE
                        WHEN m.partner_code IS NOT NULL
                         AND m.date = fc.first_date
                            THEN TRUE
                        ELSE FALSE
                    END AS is_new_client,

                    NOW() AS date_add

                FROM mapped m
                LEFT JOIN first_sku fs
                    ON m.nom_code = fs.nom_code
                LEFT JOIN first_client fc
                    ON m.partner_code = fc.partner_code
                """,
                [start_date, start_date],
            )

            inserted = cursor.rowcount

            logger.info(
                "RevenueSales insert finished: rows=%s",
                inserted,
            )

    result = {
        "revenue_sales_rows": inserted,
        "deleted": deleted,
        "start_date": start_date.isoformat() if start_date else None,
        "mode": "partial" if start_date else "full",
    }

    logger.info("RevenueSales SQL rebuild finished: %s", result)

    return result
    