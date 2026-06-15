from datasets.models import TurnoverClear, TurnoverIndicator
from analytics.clickhouse.repository import ClickHouseRepository


def sync_fb_turnover_to_clickhouse():
    repo = ClickHouseRepository()

    turnover_rows = list(
        TurnoverClear.objects.all().values(
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
        )
    )

    indicator_rows = list(
        TurnoverIndicator.objects.all().values(
            "id",
            "indicator",
            "date_start",
        )
    )

    repo.truncate_fb_turnover_use()
    repo.truncate_fb_turnover_indicator()

    inserted_turnover = repo.insert_fb_turnover_use_rows(turnover_rows)
    inserted_indicator = repo.insert_fb_turnover_indicator_rows(indicator_rows)

    return {
        "fb_turnover_use": inserted_turnover,
        "fb_turnover_ind": inserted_indicator,
    }