import json

from analytics.clickhouse.client import get_clickhouse_client
from analytics.clickhouse.schema import (
    ensure_dataset_rows_table,
    ensure_fb_project_table,
    ensure_yd_wordstat_for_table,
    ensure_fb_purchases_use_table,
    ensure_fb_purchases_indicator_table,
    ensure_fb_turnover_use_table,
    ensure_fb_turnover_indicator_table,
)
from datetime import date, datetime


FB_PROJECT_COLUMNS = [
    "id",
    "folder_lvl1",
    "folder_lvl2",
    "folder_lvl3",
    "project_name",
    "project_manager",
    "start_date",
    "end_date",
    "project_status",
    "project_type",
    "department",
    "subtask_id",
    "subtask_name",
    "subtask_responsible",
    "subtask_start_date",
    "subtask_end_date",
    "actual_start_project",
    "actual_end_project",
    "actual_start_subtask",
    "actual_end_subtask",
    "subtask_status",
    "m_quarter_text",
    "deviation",
    "deviation_project",
    "number",
    "predecessor",
    "code_sdr",
    "type_depend",
    "delay",
    "unit",
    "hier_subtask1",
    "hier_subtask2",
    "hier_subtask3",
    "hier_subtask4",
    "hier_subtask5",
    "hier_subtask6",
    "hier_subtask7",
    "hier_subtask8",
    "hier_subtask9",
    "hier_subtask10",
]

FB_PROJECT_DATE_COLUMNS = {
    "start_date",
    "end_date",
    "subtask_start_date",
    "subtask_end_date",
    "actual_start_project",
    "actual_end_project",
    "actual_start_subtask",
    "actual_end_subtask",
}



YD_WORDSTAT_COLUMNS = [
    "id",
    "feature",
    "category",
    "phrase",
    "year",
    "month_1",
    "month_2",
    "month_3",
    "month_4",
    "month_5",
    "month_6",
    "month_7",
    "month_8",
    "month_9",
    "month_10",
    "month_11",
    "month_12",
    "total",
    "average",
    "growth",
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
    "desktop",
    "phone",
    "tablet",
    "other_device",
    "ekb_macroregion",
    "kras_macroregion",
    "mos_macroregion",
    "nign_macroregion",
    "novos_macroregion",
    "spb_macroregion",
    "sng_macroregion",
    "other_macroregion",
]



FB_PURCHASES_USE_COLUMNS = [
    "id",
    "quantity_1C",
    "revenue_1C",
    "VAT_1C",
    "nomenclature_code",
    "date_draft",
    "party_status",
    "partner",
    "nomenclature",
]


FB_PURCHASES_INDICATOR_COLUMNS = [
    "id",
    "indicator",
    "date_draft",
]



FB_TURNOVER_USE_COLUMNS = [
    "id",
    "date_stock",
    "date_start",
    "date_end",
    "warehouse_group",
    "warehouse",
    "nomenclature",
    "quantity",
    "price",
    "amount_day",
    "middle_stock",
    "middle_rubstock",
]


FB_TURNOVER_INDICATOR_COLUMNS = [
    "id",
    "indicator",
    "date_start",
]







def normalize_fb_project_value(value, column=None):
    if column in FB_PROJECT_DATE_COLUMNS:
        if value in (None, ""):
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return None

        return None

    if value is None:
        return ""

    return value






class ClickHouseRepository:

    def insert_dataset_rows(self, dataset_id: int, rows: list):
        ensure_dataset_rows_table()

        client = get_clickhouse_client()

        payload = [
            (
                dataset_id,
                json.dumps(row)
            )
            for row in rows
        ]

        if not payload:
            return

        client.execute(
            """
            INSERT INTO default.dataset_rows
            (dataset_id, data)
            VALUES
            """,
            payload,
        )

    def fetch_dataset_rows(self, dataset_id: int):
        ensure_dataset_rows_table()

        client = get_clickhouse_client()

        rows = client.execute(
            """
            SELECT data
            FROM default.dataset_rows
            WHERE dataset_id = %(dataset_id)s
            """,
            {"dataset_id": dataset_id},
        )

        return [
            json.loads(row[0])
            for row in rows
        ]
    




    def truncate_fb_project(self):
        ensure_fb_project_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.fb_project
        """)

    def insert_fb_project_rows(self, rows: list[dict]):
        ensure_fb_project_table()

        client = get_clickhouse_client()

        payload = []

        for row in rows:
            payload.append(
                tuple(
                    normalize_fb_project_value(row.get(column), column)
                    for column in FB_PROJECT_COLUMNS
                )
            )

        if not payload:
            return

        columns_sql = ", ".join(FB_PROJECT_COLUMNS)

        client.execute(
            f"""
            INSERT INTO default.fb_project
            ({columns_sql})
            VALUES
            """,
            payload,
        )


    def fetch_fb_project_rows(self, filters: dict | None = None):
        ensure_fb_project_table()

        filters = filters or {}

        client = get_clickhouse_client()

        where = []
        params = {}

        string_filters = [
            "project_name",
            "project_type",
            "department",
            "deviation_project",
            "project_manager",
            "project_status",
            "folder_lvl1",
            "folder_lvl2",
            "folder_lvl3",
        ]

        for field in string_filters:
            value = filters.get(field)
            if value:
                where.append(f"{field} = %({field})s")
                params[field] = value

        if filters.get("project_start"):
            where.append("start_date >= %(project_start)s")
            params["project_start"] = filters["project_start"]

        if filters.get("project_end"):
            where.append("end_date <= %(project_end)s")
            params["project_end"] = filters["project_end"]

        where_sql = ""

        if where:
            where_sql = "WHERE " + " AND ".join(where)

        columns_sql = ", ".join(FB_PROJECT_COLUMNS)

        result = client.execute(
            f"""
            SELECT {columns_sql}
            FROM default.fb_project
            {where_sql}
            ORDER BY id
            """,
            params,
        )

        rows = []

        for item in result:
            rows.append(
                dict(zip(FB_PROJECT_COLUMNS, item))
            )

        return rows






    def truncate_yd_wordstat_for(self):
        ensure_yd_wordstat_for_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.yd_wordstat_for
        """)

    def insert_yd_wordstat_rows(self, rows: list[dict]):
        ensure_yd_wordstat_for_table()

        client = get_clickhouse_client()

        payload = []

        for row in rows:
            payload.append(
                tuple(
                    row.get(column)
                    for column in YD_WORDSTAT_COLUMNS
                )
            )

        if not payload:
            return

        columns_sql = ", ".join(YD_WORDSTAT_COLUMNS)

        client.execute(
            f"""
            INSERT INTO default.yd_wordstat_for
            ({columns_sql})
            VALUES
            """,
            payload,
        )

    def fetch_yd_wordstat_rows(self, filters: dict | None = None):
        ensure_yd_wordstat_for_table()

        filters = filters or {}

        client = get_clickhouse_client()

        where = []
        params = {}

        list_filters = [
            "feature",
            "category",
            "phrase",
        ]

        for field in list_filters:
            value = filters.get(field)

            if not value:
                continue

            if isinstance(value, str):
                value = [value]

            where.append(f"{field} IN %({field})s")
            params[field] = tuple(value)

        where_sql = ""

        if where:
            where_sql = "WHERE " + " AND ".join(where)

        columns_sql = ", ".join(YD_WORDSTAT_COLUMNS)

        result = client.execute(
            f"""
            SELECT {columns_sql}
            FROM default.yd_wordstat_for
            {where_sql}
            ORDER BY category, feature, phrase, year
            """,
            params,
        )

        return [
            dict(zip(YD_WORDSTAT_COLUMNS, item))
            for item in result
        ]





    def truncate_fb_purchases_use(self):
        ensure_fb_purchases_use_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.fb_purchases_use
        """)

    def truncate_fb_purchases_indicator(self):
        ensure_fb_purchases_indicator_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.fb_purchases_ind
        """)

    def insert_fb_purchases_use_rows(self, rows):
        ensure_fb_purchases_use_table()

        client = get_clickhouse_client()

        if not rows:
            return 0

        payload = []

        for row in rows:
            payload.append(
                tuple(row.get(col) for col in FB_PURCHASES_USE_COLUMNS)
            )

        columns_sql = ", ".join(FB_PURCHASES_USE_COLUMNS)

        client.execute(
            f"""
            INSERT INTO default.fb_purchases_use
            ({columns_sql})
            VALUES
            """,
            payload,
        )

        return len(payload)

    def insert_fb_purchases_indicator_rows(self, rows):
        ensure_fb_purchases_indicator_table()

        client = get_clickhouse_client()

        if not rows:
            return 0

        payload = []

        for row in rows:
            payload.append(
                tuple(row.get(col) for col in FB_PURCHASES_INDICATOR_COLUMNS)
            )

        columns_sql = ", ".join(FB_PURCHASES_INDICATOR_COLUMNS)

        client.execute(
            f"""
            INSERT INTO default.fb_purchases_ind
            ({columns_sql})
            VALUES
            """,
            payload,
        )

        return len(payload)

    def fetch_fb_purchases_use_rows(self, filters=None):
        ensure_fb_purchases_use_table()

        filters = filters or {}

        client = get_clickhouse_client()

        where = []
        params = {}

        if filters.get("nomenclature_code"):
            where.append("nomenclature_code = %(nomenclature_code)s")
            params["nomenclature_code"] = filters["nomenclature_code"]

        if filters.get("nomenclature"):
            where.append("nomenclature = %(nomenclature)s")
            params["nomenclature"] = filters["nomenclature"]

        if filters.get("partner"):
            where.append("partner = %(partner)s")
            params["partner"] = filters["partner"]

        if filters.get("date_start"):
            where.append("date_draft >= %(date_start)s")
            params["date_start"] = filters["date_start"]

        if filters.get("date_end"):
            where.append("date_draft <= %(date_end)s")
            params["date_end"] = filters["date_end"]

        where_sql = ""

        if where:
            where_sql = "WHERE " + " AND ".join(where)

        columns_sql = ", ".join(FB_PURCHASES_USE_COLUMNS)

        result = client.execute(
            f"""
            SELECT {columns_sql}
            FROM default.fb_purchases_use
            {where_sql}
            ORDER BY date_draft DESC, nomenclature_code, nomenclature, partner
            """,
            params,
        )

        return [
            dict(zip(FB_PURCHASES_USE_COLUMNS, row))
            for row in result
        ]

    def fetch_fb_purchases_indicator_rows(self, filters=None):
        ensure_fb_purchases_indicator_table()

        filters = filters or {}

        client = get_clickhouse_client()

        where = []
        params = {}

        if filters.get("date_start"):
            where.append("date_draft >= %(date_start)s")
            params["date_start"] = filters["date_start"]

        if filters.get("date_end"):
            where.append("date_draft <= %(date_end)s")
            params["date_end"] = filters["date_end"]

        where_sql = ""

        if where:
            where_sql = "WHERE " + " AND ".join(where)

        columns_sql = ", ".join(FB_PURCHASES_INDICATOR_COLUMNS)

        result = client.execute(
            f"""
            SELECT {columns_sql}
            FROM default.fb_purchases_ind
            {where_sql}
            ORDER BY date_draft
            """,
            params,
        )

        return [
            dict(zip(FB_PURCHASES_INDICATOR_COLUMNS, row))
            for row in result
        ]






    def truncate_fb_turnover_use(self):
        ensure_fb_turnover_use_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.fb_turnover_use
        """)

    def truncate_fb_turnover_indicator(self):
        ensure_fb_turnover_indicator_table()

        client = get_clickhouse_client()

        client.execute("""
            TRUNCATE TABLE default.fb_turnover_ind
        """)

    def insert_fb_turnover_use_rows(self, rows):
        ensure_fb_turnover_use_table()

        client = get_clickhouse_client()

        if not rows:
            return 0

        payload = []

        for row in rows:
            payload.append(
                tuple(row.get(col) for col in FB_TURNOVER_USE_COLUMNS)
            )

        columns_sql = ", ".join(FB_TURNOVER_USE_COLUMNS)

        client.execute(
            f"""
            INSERT INTO default.fb_turnover_use
            ({columns_sql})
            VALUES
            """,
            payload,
        )

        return len(payload)

    def insert_fb_turnover_indicator_rows(self, rows):
        ensure_fb_turnover_indicator_table()

        client = get_clickhouse_client()

        if not rows:
            return 0

        payload = []

        for row in rows:
            payload.append(
                tuple(row.get(col) for col in FB_TURNOVER_INDICATOR_COLUMNS)
            )

        columns_sql = ", ".join(FB_TURNOVER_INDICATOR_COLUMNS)

        client.execute(
            f"""
            INSERT INTO default.fb_turnover_ind
            ({columns_sql})
            VALUES
            """,
            payload,
        )

        return len(payload)

    def fetch_fb_turnover_use_rows(self, filters=None):
        ensure_fb_turnover_use_table()

        filters = filters or {}

        client = get_clickhouse_client()

        where = []
        params = {}

        if filters.get("nomenclature"):
            where.append("nomenclature = %(nomenclature)s")
            params["nomenclature"] = filters["nomenclature"]

        if filters.get("warehouse_group"):
            where.append("warehouse_group = %(warehouse_group)s")
            params["warehouse_group"] = filters["warehouse_group"]

        if filters.get("warehouse"):
            where.append("warehouse = %(warehouse)s")
            params["warehouse"] = filters["warehouse"]

        if filters.get("quantity"):
            where.append("quantity = %(quantity)s")
            params["quantity"] = filters["quantity"]

        if filters.get("date_start"):
            where.append("date_start >= %(date_start)s")
            params["date_start"] = filters["date_start"]

        if filters.get("date_end"):
            where.append("date_end <= %(date_end)s")
            params["date_end"] = filters["date_end"]

        where_sql = ""

        if where:
            where_sql = "WHERE " + " AND ".join(where)

        columns_sql = ", ".join(FB_TURNOVER_USE_COLUMNS)

        result = client.execute(
            f"""
            SELECT {columns_sql}
            FROM default.fb_turnover_use
            {where_sql}
            ORDER BY date_end DESC, nomenclature, warehouse_group, warehouse, quantity
            """,
            params,
        )

        return [
            dict(zip(FB_TURNOVER_USE_COLUMNS, row))
            for row in result
        ]

    def fetch_fb_turnover_indicator_rows(self, filters=None):
        ensure_fb_turnover_indicator_table()

        filters = filters or {}

        client = get_clickhouse_client()

        where = []
        params = {}

        if filters.get("date_start"):
            where.append("date_start >= %(date_start)s")
            params["date_start"] = filters["date_start"]

        if filters.get("date_end"):
            where.append("date_start <= %(date_end)s")
            params["date_end"] = filters["date_end"]

        where_sql = ""

        if where:
            where_sql = "WHERE " + " AND ".join(where)

        columns_sql = ", ".join(FB_TURNOVER_INDICATOR_COLUMNS)

        result = client.execute(
            f"""
            SELECT {columns_sql}
            FROM default.fb_turnover_ind
            {where_sql}
            ORDER BY date_start
            """,
            params,
        )

        return [
            dict(zip(FB_TURNOVER_INDICATOR_COLUMNS, row))
            for row in result
        ]