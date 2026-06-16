from datasets.models import AccreceivUse, AccreceivIndicator
from analytics.clickhouse.repository import ClickHouseRepository


def sync_fb_accreceiv_to_clickhouse():
    repo = ClickHouseRepository()

    accreceiv_rows = list(
        AccreceivUse.objects.all().values(
            "id",
            "date_start",
            "date_end",
            "partner",
            "contract_partner",
            "manager_name",
            "mutual_instock",
            "mutual_comstock",
            "mutual_spenstock",
            "mutual_finstock",
            "initial_stock",
            "coming_stock",
            "spending_stock",
            "final_stock",
        )
    )

    indicator_rows = list(
        AccreceivIndicator.objects.all().values(
            "id",
            "manager_name",
        )
    )

    repo.truncate_fb_accreceiv_use()
    repo.truncate_fb_accreceiv_indicator()

    inserted_accreceiv = repo.insert_fb_accreceiv_use_rows(accreceiv_rows)
    inserted_indicator = repo.insert_fb_accreceiv_indicator_rows(indicator_rows)

    return {
        "fb_accreceiv_use": inserted_accreceiv,
        "fb_accreceiv_ind": inserted_indicator,
    }