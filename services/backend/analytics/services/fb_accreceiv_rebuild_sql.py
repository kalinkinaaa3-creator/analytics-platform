import logging

from django.db import connection, transaction


logger = logging.getLogger("external_api.fb_accreceiv")


def rebuild_fb_accreceiv_use_from_raw_sql():
    logger.info("FBAccreceivUse SQL rebuild started")

    with transaction.atomic():
        with connection.cursor() as cursor:
            logger.info("FBAccreceivUse truncate started")

            cursor.execute("""
                TRUNCATE TABLE fb_accreceiv_use RESTART IDENTITY
            """)

            logger.info("FBAccreceivUse truncate finished")

            logger.info("FBAccreceivUse insert from raw started")

            cursor.execute("""
                WITH grouped AS (
                    SELECT
                        raw.date_start,
                        raw.date_end,
                        raw.partner,
                        raw.contract_partner,
                        raw.manager_name,
                        MAX(raw.id) AS max_id,
                        SUM(raw.mutual_finstock) AS mutual_finstock_total
                    FROM fb_accreceiv_raw raw
                    GROUP BY
                        raw.date_start,
                        raw.date_end,
                        raw.partner,
                        raw.contract_partner,
                        raw.manager_name
                )
                INSERT INTO fb_accreceiv_use
                    (
                        date_start,
                        date_end,
                        partner,
                        contract_partner,
                        manager_name,
                        mutual_instock,
                        mutual_comstock,
                        mutual_spenstock,
                        mutual_finstock,
                        initial_stock,
                        coming_stock,
                        spending_stock,
                        final_stock,
                        date_add
                    )
                SELECT
                    raw.date_start,
                    raw.date_end,
                    raw.partner,
                    raw.contract_partner,
                    raw.manager_name,
                    raw.mutual_instock,
                    raw.mutual_comstock,
                    raw.mutual_spenstock,
                    grouped.mutual_finstock_total,
                    raw.initial_stock,
                    raw.coming_stock,
                    raw.spending_stock,
                    raw.final_stock,
                    raw.date_add
                FROM grouped
                INNER JOIN fb_accreceiv_raw raw
                    ON raw.id = grouped.max_id
                INNER JOIN fb_accreceiv_ind ind
                    ON raw.manager_name = ind.manager_name
                WHERE grouped.mutual_finstock_total >= 0
            """)

            inserted_rows = cursor.rowcount

            logger.info(
                "FBAccreceivUse insert from raw finished: rows=%s",
                inserted_rows,
            )

    result = {
        "fb_accreceiv_use_rows": inserted_rows,
    }

    logger.info("FBAccreceivUse SQL rebuild finished: %s", result)

    return result