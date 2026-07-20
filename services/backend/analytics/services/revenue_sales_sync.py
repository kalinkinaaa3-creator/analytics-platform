from datasets.models import RevenueSales

from analytics.clickhouse.repository import ClickHouseRepository


def sync_revenue_sales_to_clickhouse():
    repo = ClickHouseRepository()

    revenue_sales_rows = list(
        RevenueSales.objects.all().values(
            "id",
            "date",
            "direction",
            "project",
            "manager",
            "partner",
            "partner_code",
            "consignee",
            "nom_view",
            "nom_category",
            "nom_group",
            "nom",
            "nom_code",
            "nom_hier",
            "type_doc",
            "quantity",
            "weight_total",
            "revenue",
            "is_new_sku",
            "is_new_client",
            "date_add",
        )
    )

    repo.truncate_revenue_sales()
    revenue_sales_count = repo.insert_revenue_sales_rows(revenue_sales_rows)

    return {
        "revenue_sales": revenue_sales_count,
    }