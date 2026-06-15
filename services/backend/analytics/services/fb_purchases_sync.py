from datasets.models import FBPurchasesUse, FBPurchasesUseIndicator
from analytics.clickhouse.repository import ClickHouseRepository


def sync_fb_purchases_to_clickhouse():
    repo = ClickHouseRepository()

    use_rows = list(
        FBPurchasesUse.objects.all().values(
            "id",
            "quantity_1C",
            "revenue_1C",
            "VAT_1C",
            "nomenclature_code",
            "date_draft",
            "party_status",
            "partner",
            "nomenclature",
        )
    )

    indicator_rows = list(
        FBPurchasesUseIndicator.objects.all().values(
            "id",
            "indicator",
            "date_draft",
        )
    )

    repo.truncate_fb_purchases_use()
    repo.truncate_fb_purchases_indicator()

    inserted_use = repo.insert_fb_purchases_use_rows(use_rows)
    inserted_indicator = repo.insert_fb_purchases_indicator_rows(indicator_rows)

    return {
        "fb_purchases_use": inserted_use,
        "fb_purchases_ind": inserted_indicator,
    }