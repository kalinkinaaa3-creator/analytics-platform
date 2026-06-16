from datasets.models import (
    PlannedSales,
    PlanSales,
    PlannedSalesDirectory,
)

from analytics.clickhouse.repository import ClickHouseRepository


def sync_planned_sales_to_clickhouse():
    repo = ClickHouseRepository()

    planned_sales_rows = list(
        PlannedSales.objects.all().values(
            "id",
            "date",
            "level1",
            "level2",
            "level3",
            "fact",
            "appg",
            "appg_slice",
            "id_directory",
            "date_add",
        )
    )

    plan_sales_rows = list(
        PlanSales.objects.all().values(
            "id",
            "date",
            "level1",
            "level2",
            "level3",
            "plan",
            "projection_s",
            "id_directory",
            "date_add",
        )
    )

    directory_rows = list(
        PlannedSalesDirectory.objects.all().values(
            "id",
            "level1",
            "draft2",
            "level2",
            "draft3",
            "level3",
        )
    )

    repo.truncate_planned_sales()
    planned_sales_count = repo.insert_planned_sales_rows(planned_sales_rows)

    repo.truncate_plan_sales()
    plan_sales_count = repo.insert_plan_sales_rows(plan_sales_rows)

    repo.truncate_planned_sales_directory()
    directory_count = repo.insert_planned_sales_directory_rows(directory_rows)

    return {
        "planned_sales": planned_sales_count,
        "plan_sales": plan_sales_count,
        "planned_sales_directory": directory_count,
    }