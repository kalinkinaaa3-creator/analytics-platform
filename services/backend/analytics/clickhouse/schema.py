from analytics.clickhouse.client import get_clickhouse_client


def ensure_dataset_rows_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.dataset_rows
        (
            dataset_id UInt64,
            data String
        )
        ENGINE = MergeTree()
        ORDER BY dataset_id
    """)




def ensure_fb_project_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_project
        (
            id UInt64,

            folder_lvl1 String,
            folder_lvl2 String,
            folder_lvl3 String,

            project_name String,
            project_manager String,

            start_date Nullable(Date),
            end_date Nullable(Date),

            project_status String,
            project_type String,
            department String,

            subtask_id String,
            subtask_name String,
            subtask_responsible String,

            subtask_start_date Nullable(Date),
            subtask_end_date Nullable(Date),

            actual_start_project Nullable(Date),
            actual_end_project Nullable(Date),
            actual_start_subtask Nullable(Date),
            actual_end_subtask Nullable(Date),

            subtask_status String,

            m_quarter_text String,
            deviation String,
            deviation_project String,

            number Nullable(Int64),

            predecessor String,
            code_sdr String,
            type_depend String,
            delay String,
            unit String,

            hier_subtask1 String,
            hier_subtask2 String,
            hier_subtask3 String,
            hier_subtask4 String,
            hier_subtask5 String,
            hier_subtask6 String,
            hier_subtask7 String,
            hier_subtask8 String,
            hier_subtask9 String,
            hier_subtask10 String
        )
        ENGINE = MergeTree()
        ORDER BY (folder_lvl1, department, project_name, id)
    """)