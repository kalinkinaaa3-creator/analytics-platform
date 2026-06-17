import logging

from django.db import connection, transaction


logger = logging.getLogger("external_api.fb_turnover")


def rebuild_fb_turnover_use_from_raw_sql():
    logger.info("FBTurnoverUse SQL rebuild started")

    with transaction.atomic():
        with connection.cursor() as cursor:
            logger.info("FBTurnoverUse truncate started")

            cursor.execute("""
                TRUNCATE TABLE fb_turnover_use RESTART IDENTITY
            """)

            logger.info("FBTurnoverUse truncate finished")

            logger.info("FBTurnoverUse insert from raw started")

            cursor.execute("""
                INSERT INTO fb_turnover_use
                    (
                        date_stock,
                        date_start,
                        date_end,
                        warehouse_group,
                        warehouse,
                        nomenclature,
                        quantity,
                        price,
                        amount_day,
                        middle_stock,
                        middle_rubstock,
                        date_add
                    )
                SELECT
                    date_stock,
                    date_start,
                    date_end,
                    warehouse_group,
                    warehouse,
                    nomenclature,
                    quantity,
                    price,
                    amount_day,
                    middle_stock,
                    middle_rubstock,
                    date_add
                FROM fb_turnover_raw
                WHERE
                    (
                        EXTRACT(YEAR FROM date_end) = EXTRACT(YEAR FROM CURRENT_DATE)
                        AND EXTRACT(MONTH FROM date_end) = EXTRACT(MONTH FROM CURRENT_DATE)
                    )
                    OR
                    date_end = (
                        date_trunc('month', date_end)::date
                        + INTERVAL '1 month'
                        - INTERVAL '1 day'
                    )::date
            """)

            inserted_rows = cursor.rowcount

            logger.info(
                "FBTurnoverUse insert from raw finished: rows=%s",
                inserted_rows,
            )

    result = {
        "fb_turnover_use_rows": inserted_rows,
    }

    logger.info("FBTurnoverUse SQL rebuild finished: %s", result)

    return result