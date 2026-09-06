import logging

from django.db import connection, transaction


logger = logging.getLogger("external_api.yd_wordstat")


def rebuild_yd_wordstat_for_from_raw_sql():
    logger.info("YD Wordstat rebuild started")

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE yd_wordstat_all AS raw
                SET
                    feature = ref.feature,
                    category = ref.category
                FROM yd_wordstat_ref AS ref
                WHERE raw.phrase = ref.phrase
                  AND (raw.feature IS NULL OR raw.category IS NULL)
            """)

            cursor.execute("""
                UPDATE yd_wordstat_device AS raw
                SET
                    feature = ref.feature,
                    category = ref.category
                FROM yd_wordstat_ref AS ref
                WHERE raw.phrase = ref.phrase
                  AND (raw.feature IS NULL OR raw.category IS NULL)
            """)

            cursor.execute("TRUNCATE TABLE yd_wordstat_for RESTART IDENTITY")

            cursor.execute("""
                INSERT INTO yd_wordstat_for (
                    feature,
                    category,
                    phrase,
                    year,

                    month_1,
                    month_2,
                    month_3,
                    month_4,
                    month_5,
                    month_6,
                    month_7,
                    month_8,
                    month_9,
                    month_10,
                    month_11,
                    month_12,

                    total,
                    average,
                    growth,

                    "monthS_1",
                    "monthS_2",
                    "monthS_3",
                    "monthS_4",
                    "monthS_5",
                    "monthS_6",
                    "monthS_7",
                    "monthS_8",
                    "monthS_9",
                    "monthS_10",
                    "monthS_11",
                    "monthS_12",

                    desktop,
                    phone,
                    tablet,
                    other_device,

                    ekb_macroregion,
                    kras_macroregion,
                    mos_macroregion,
                    nign_macroregion,
                    novos_macroregion,
                    spb_macroregion,
                    sng_macroregion,
                    other_macroregion,

                    date_add
                )
                WITH all_months AS (
                    SELECT
                        feature,
                        category,
                        phrase,
                        EXTRACT(YEAR FROM date)::int AS year,

                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 1) AS month_1,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 2) AS month_2,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 3) AS month_3,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 4) AS month_4,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 5) AS month_5,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 6) AS month_6,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 7) AS month_7,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 8) AS month_8,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 9) AS month_9,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 10) AS month_10,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 11) AS month_11,
                        SUM(count) FILTER (WHERE EXTRACT(MONTH FROM date)::int = 12) AS month_12
                    FROM yd_wordstat_all
                    GROUP BY
                        feature,
                        category,
                        phrase,
                        EXTRACT(YEAR FROM date)::int
                ),
                all_calc AS (
                    SELECT
                        *,
                        (
                            COALESCE(month_1, 0)
                            + COALESCE(month_2, 0)
                            + COALESCE(month_3, 0)
                            + COALESCE(month_4, 0)
                            + COALESCE(month_5, 0)
                            + COALESCE(month_6, 0)
                            + COALESCE(month_7, 0)
                            + COALESCE(month_8, 0)
                            + COALESCE(month_9, 0)
                            + COALESCE(month_10, 0)
                            + COALESCE(month_11, 0)
                            + COALESCE(month_12, 0)
                        ) AS total,
                        (
                            SELECT AVG(value)
                            FROM (
                                VALUES
                                    (month_1),
                                    (month_2),
                                    (month_3),
                                    (month_4),
                                    (month_5),
                                    (month_6),
                                    (month_7),
                                    (month_8),
                                    (month_9),
                                    (month_10),
                                    (month_11),
                                    (month_12)
                            ) AS month_values(value)
                            WHERE value IS NOT NULL
                        ) AS average
                    FROM all_months
                ),
                all_growth AS (
                    SELECT
                        *,
                        LAG(average) OVER (
                            PARTITION BY feature, category, phrase
                            ORDER BY year
                        ) AS prev_year_average
                    FROM all_calc
                ),
                device_year AS (
                    SELECT
                        phrase,
                        EXTRACT(YEAR FROM date)::int AS year,
                        SUM(count) FILTER (WHERE device = 'desktop') AS desktop,
                        SUM(count) FILTER (WHERE device = 'phone') AS phone,
                        SUM(count) FILTER (WHERE device = 'tablet') AS tablet
                    FROM yd_wordstat_device
                    GROUP BY
                        phrase,
                        EXTRACT(YEAR FROM date)::int
                ),
                macroregion_year AS (
                    SELECT
                        phrase,
                        EXTRACT(YEAR FROM date)::int AS year,
                        SUM(count) FILTER (WHERE macroregion_label = 'ЕКАТЕРИНБУРГ') AS ekb_macroregion,
                        SUM(count) FILTER (WHERE macroregion_label = 'КРАСНОДАР') AS kras_macroregion,
                        SUM(count) FILTER (WHERE macroregion_label = 'МОСКВА') AS mos_macroregion,
                        SUM(count) FILTER (WHERE macroregion_label = 'НИЖНЕКАМСК') AS nign_macroregion,
                        SUM(count) FILTER (WHERE macroregion_label = 'НОВОСИБИРСК') AS novos_macroregion,
                        SUM(count) FILTER (WHERE macroregion_label = 'СПБ') AS spb_macroregion,
                        SUM(count) FILTER (WHERE macroregion_label = 'СНГ') AS sng_macroregion
                    FROM yd_wordstat_iplast_api
                    GROUP BY
                        phrase,
                        EXTRACT(YEAR FROM date)::int
                )
                SELECT
                    all_growth.feature,
                    all_growth.category,
                    all_growth.phrase,
                    all_growth.year,

                    COALESCE(all_growth.month_1, 0),
                    COALESCE(all_growth.month_2, 0),
                    COALESCE(all_growth.month_3, 0),
                    COALESCE(all_growth.month_4, 0),
                    COALESCE(all_growth.month_5, 0),
                    COALESCE(all_growth.month_6, 0),
                    COALESCE(all_growth.month_7, 0),
                    COALESCE(all_growth.month_8, 0),
                    COALESCE(all_growth.month_9, 0),
                    COALESCE(all_growth.month_10, 0),
                    COALESCE(all_growth.month_11, 0),
                    COALESCE(all_growth.month_12, 0),

                    COALESCE(all_growth.total, 0),

                    ROUND(COALESCE(all_growth.average, 0)::numeric, 2),

                    ROUND(
                        CASE
                            WHEN all_growth.prev_year_average IS NULL THEN 0
                            WHEN all_growth.prev_year_average = 0 AND COALESCE(all_growth.average, 0) > 0 THEN 100
                            WHEN all_growth.prev_year_average = 0 THEN 0
                            ELSE ((all_growth.average / all_growth.prev_year_average) - 1) * 100
                        END::numeric,
                        2
                    ),

                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_1, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_2, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_3, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_4, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_5, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_6, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_7, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_8, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_9, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_10, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_11, 0) / all_growth.average END::numeric, 2),
                    ROUND(CASE WHEN COALESCE(all_growth.average, 0) = 0 THEN 0 ELSE COALESCE(all_growth.month_12, 0) / all_growth.average END::numeric, 2),

                    COALESCE(device_year.desktop, 0),
                    COALESCE(device_year.phone, 0),
                    COALESCE(device_year.tablet, 0),

                    (
                        COALESCE(all_growth.total, 0)
                        - (
                            COALESCE(device_year.desktop, 0)
                            + COALESCE(device_year.phone, 0)
                            + COALESCE(device_year.tablet, 0)
                        )
                    ),

                    COALESCE(macroregion_year.ekb_macroregion, 0),
                    COALESCE(macroregion_year.kras_macroregion, 0),
                    COALESCE(macroregion_year.mos_macroregion, 0),
                    COALESCE(macroregion_year.nign_macroregion, 0),
                    COALESCE(macroregion_year.novos_macroregion, 0),
                    COALESCE(macroregion_year.spb_macroregion, 0),
                    COALESCE(macroregion_year.sng_macroregion, 0),

                    (
                        COALESCE(all_growth.total, 0)
                        - (
                            COALESCE(macroregion_year.ekb_macroregion, 0)
                            + COALESCE(macroregion_year.kras_macroregion, 0)
                            + COALESCE(macroregion_year.mos_macroregion, 0)
                            + COALESCE(macroregion_year.nign_macroregion, 0)
                            + COALESCE(macroregion_year.novos_macroregion, 0)
                            + COALESCE(macroregion_year.spb_macroregion, 0)
                            + COALESCE(macroregion_year.sng_macroregion, 0)
                        )
                    ),

                    NOW() AS date_add

                FROM all_growth
                LEFT JOIN device_year
                    ON device_year.phrase = all_growth.phrase
                   AND device_year.year = all_growth.year
                LEFT JOIN macroregion_year
                    ON macroregion_year.phrase = all_growth.phrase
                   AND macroregion_year.year = all_growth.year
            """)

            cursor.execute("SELECT COUNT(*) FROM yd_wordstat_for")
            total_for = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM yd_wordstat_iplast_api")
            total_macroregion = cursor.fetchone()[0]

    result = {
        "yd_wordstat_for": total_for,
        "yd_wordstat_iplast_api": total_macroregion,
    }

    logger.info("YD Wordstat rebuild finished: %s", result)

    return result
