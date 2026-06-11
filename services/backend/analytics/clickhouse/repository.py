import json

from analytics.clickhouse.client import get_clickhouse_client
from analytics.clickhouse.schema import (
    ensure_dataset_rows_table,
    ensure_fb_project_table,
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