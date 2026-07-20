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




def ensure_yd_wordstat_for_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.yd_wordstat_for
        (
            id UInt64,

            feature String,
            category String,
            phrase String,
            year Int64,

            month_1 Nullable(Int64),
            month_2 Nullable(Int64),
            month_3 Nullable(Int64),
            month_4 Nullable(Int64),
            month_5 Nullable(Int64),
            month_6 Nullable(Int64),
            month_7 Nullable(Int64),
            month_8 Nullable(Int64),
            month_9 Nullable(Int64),
            month_10 Nullable(Int64),
            month_11 Nullable(Int64),
            month_12 Nullable(Int64),

            total Nullable(Int64),
            average Nullable(Float64),
            growth Nullable(Float64),

            monthS_1 Nullable(Float64),
            monthS_2 Nullable(Float64),
            monthS_3 Nullable(Float64),
            monthS_4 Nullable(Float64),
            monthS_5 Nullable(Float64),
            monthS_6 Nullable(Float64),
            monthS_7 Nullable(Float64),
            monthS_8 Nullable(Float64),
            monthS_9 Nullable(Float64),
            monthS_10 Nullable(Float64),
            monthS_11 Nullable(Float64),
            monthS_12 Nullable(Float64),

            desktop Nullable(Int64),
            phone Nullable(Int64),
            tablet Nullable(Int64),
            other_device Nullable(Int64),

            ekb_macroregion Nullable(Int64),
            kras_macroregion Nullable(Int64),
            mos_macroregion Nullable(Int64),
            nign_macroregion Nullable(Int64),
            novos_macroregion Nullable(Int64),
            spb_macroregion Nullable(Int64),
            sng_macroregion Nullable(Int64),
            other_macroregion Nullable(Int64)
        )
        ENGINE = MergeTree()
        ORDER BY (feature, category, phrase, year, id)
    """)



def ensure_fb_purchases_use_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_purchases_use
        (
            id UInt64,
            quantity_1C Nullable(Decimal(15, 0)),
            revenue_1C Nullable(Decimal(20, 2)),
            VAT_1C Nullable(Decimal(20, 2)),

            nomenclature_code String,
            date_draft Date,
            party_status String,
            partner String,
            nomenclature String
        )
        ENGINE = MergeTree()
        ORDER BY (date_draft, nomenclature_code, nomenclature, partner, id)
    """)


def ensure_fb_purchases_indicator_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_purchases_ind
        (
            id UInt64,
            indicator Nullable(Decimal(9, 2)),
            date_draft Date
        )
        ENGINE = MergeTree()
        ORDER BY (date_draft, id)
    """)




def ensure_fb_turnover_use_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_turnover_use
        (
            id UInt64,

            date_stock Date,
            date_start Date,
            date_end Date,

            warehouse_group String,
            warehouse String,
            nomenclature String,
            quantity String,

            price Nullable(Decimal(9, 2)),
            amount_day Nullable(Int32),
            middle_stock Nullable(Decimal(10, 2)),
            middle_rubstock Nullable(Decimal(12, 2))
        )
        ENGINE = MergeTree()
        ORDER BY (date_end, date_start, nomenclature, warehouse_group, warehouse, id)
    """)


def ensure_fb_turnover_indicator_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_turnover_ind
        (
            id UInt64,
            indicator Int64,
            date_start Date
        )
        ENGINE = MergeTree()
        ORDER BY (date_start, id)
    """)




def ensure_fb_accreceiv_use_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_accreceiv_use
        (
            id UInt64,

            date_start Date,
            date_end Date,

            partner String,
            contract_partner String,
            manager_name String,

            mutual_instock Nullable(Decimal(12, 2)),
            mutual_comstock Nullable(Decimal(12, 2)),
            mutual_spenstock Nullable(Decimal(12, 2)),
            mutual_finstock Nullable(Decimal(12, 2)),

            initial_stock Nullable(Decimal(12, 2)),
            coming_stock Nullable(Decimal(12, 2)),
            spending_stock Nullable(Decimal(12, 2)),
            final_stock Nullable(Decimal(12, 2))
        )
        ENGINE = MergeTree()
        ORDER BY (date_start, date_end, partner, contract_partner, manager_name, id)
    """)


def ensure_fb_accreceiv_indicator_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.fb_accreceiv_ind
        (
            id UInt64,
            manager_name String
        )
        ENGINE = MergeTree()
        ORDER BY (manager_name, id)
    """)







def ensure_planned_sales_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.planned_sales
        (
            id UInt64,
            date Date,

            level1 String,
            level2 String,
            level3 String,

            fact Nullable(Decimal(14, 2)),
            appg Nullable(Decimal(14, 2)),
            appg_slice Nullable(Decimal(14, 2)),

            id_directory Int64,
            date_add DateTime
        )
        ENGINE = MergeTree()
        ORDER BY (date, id_directory, id)
    """)


def ensure_plan_sales_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.plan_sales
        (
            id UInt64,
            date Date,

            level1 String,
            level2 String,
            level3 String,

            plan Nullable(Decimal(14, 2)),
            projection_s Nullable(Decimal(14, 2)),

            id_directory Int64,
            date_add DateTime
        )
        ENGINE = MergeTree()
        ORDER BY (date, id_directory, id)
    """)


def ensure_planned_sales_directory_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.planned_sales_directory
        (
            id UInt64,

            level1 String,
            draft2 String,
            level2 String,
            draft3 String,
            level3 String
        )
        ENGINE = MergeTree()
        ORDER BY (level1, level2, level3, id)
    """)




def ensure_revenue_sales_table():
    client = get_clickhouse_client()

    client.execute("""
        CREATE TABLE IF NOT EXISTS default.revenue_sales
        (
            id UInt64,
            date Date,

            direction String,
            project String,
            manager String,

            partner String,
            partner_code Nullable(Int64),
            consignee String,

            nom_view String,
            nom_category String,
            nom_group String,
            nom String,
            nom_code Nullable(Int64),

            type_doc String,

            quantity Nullable(Decimal(15, 0)),
            weight_total Nullable(Decimal(12, 2)),
            revenue Nullable(Decimal(20, 2)),

            is_new_sku UInt8,
            is_new_client UInt8,

            date_add DateTime
        )
        ENGINE = MergeTree()
        ORDER BY (
            date,
            direction,
            project,
            manager,
            partner,
            consignee,
            nom_view,
            nom_category,
            nom_group,
            nom,
            id
        )
    """)