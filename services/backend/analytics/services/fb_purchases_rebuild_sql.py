import logging

from django.db import connection, transaction


logger = logging.getLogger("external_api.fb_purchases")


def rebuild_fb_purchases_use_from_raw_sql():
    logger.info("FBPurchasesUse SQL rebuild started")

    with transaction.atomic():
        with connection.cursor() as cursor:
            logger.info("FBPurchasesUse truncate started")

            cursor.execute("""
                TRUNCATE TABLE fb_purchases_use RESTART IDENTITY
            """)

            logger.info("FBPurchasesUse truncate finished")

            logger.info("FBPurchasesUse insert from raw started")

            cursor.execute("""
                INSERT INTO fb_purchases_use
                    (
                        "quantity_1C",
                        "revenue_1C",
                        "VAT_1C",
                        nomenclature_code,
                        date_draft,
                        party_status,
                        partner,
                        nomenclature,
                        date_add
                    )

                SELECT
                    SUM("quantity_1C_110") AS "quantity_1C",
                    SUM("revenue_1C_110") AS "revenue_1C",
                    SUM("VAT_1C_110") AS "VAT_1C",
                    'Полиэтилен 110' AS nomenclature_code,
                    date_draft,
                    party_status,
                    partner,
                    nomenclature,
                    MAX(date_add) AS date_add
                FROM fb_purchases_raw
                GROUP BY date_draft, party_status, partner, nomenclature

                UNION ALL

                SELECT
                    SUM("quantity_1C_112") AS "quantity_1C",
                    SUM("revenue_1C_112") AS "revenue_1C",
                    SUM("VAT_1C_112") AS "VAT_1C",
                    'Полипропилен Блоксополимеры 112' AS nomenclature_code,
                    date_draft,
                    party_status,
                    partner,
                    nomenclature,
                    MAX(date_add) AS date_add
                FROM fb_purchases_raw
                GROUP BY date_draft, party_status, partner, nomenclature

                UNION ALL

                SELECT
                    SUM("quantity_1C_100753") AS "quantity_1C",
                    SUM("revenue_1C_100753") AS "revenue_1C",
                    SUM("VAT_1C_100753") AS "VAT_1C",
                    'Полипропилен Гомополимеры 100753' AS nomenclature_code,
                    date_draft,
                    party_status,
                    partner,
                    nomenclature,
                    MAX(date_add) AS date_add
                FROM fb_purchases_raw
                GROUP BY date_draft, party_status, partner, nomenclature
            """)

            inserted_rows = cursor.rowcount

            logger.info(
                "FBPurchasesUse insert from raw finished: rows=%s",
                inserted_rows,
            )

    result = {
        "fb_purchases_use_rows": inserted_rows,
    }

    logger.info("FBPurchasesUse SQL rebuild finished: %s", result)

    return result