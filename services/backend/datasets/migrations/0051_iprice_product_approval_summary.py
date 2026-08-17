from decimal import Decimal
from statistics import median

from django.db import migrations, models


def populate_product_approval_summaries(apps, schema_editor):
    product_model = apps.get_model(
        "datasets",
        "IPriceSnapshotProduct",
    )
    region_model = apps.get_model(
        "datasets",
        "IPriceSnapshotRegion",
    )
    approval_model = apps.get_model(
        "datasets",
        "IPriceSnapshotApproval",
    )

    for product in product_model.objects.all().iterator(
        chunk_size=500,
    ):
        regions = list(
            region_model.objects.filter(
                snapshot_product_id=product.id,
            ).values_list("id", "default_approved_rrp")
        )
        approval_by_region = dict(
            approval_model.objects.filter(
                snapshot_region_id__in=[row[0] for row in regions],
                is_current=True,
            ).values_list("snapshot_region_id", "approved_rrp")
        )
        values = [
            Decimal(approval_by_region.get(region_id, default_rrp))
            for region_id, default_rrp in regions
            if approval_by_region.get(region_id, default_rrp) is not None
        ]
        approved_median = Decimal(median(values)) if values else None
        retail_median = product.current_retail_median
        delta = (
            Decimal(retail_median) - approved_median
            if retail_median is not None and approved_median is not None
            else None
        )
        product_model.objects.filter(pk=product.id).update(
            effective_approved_rrp_median=approved_median,
            current_vs_approved_amount=delta,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0050_granular_iprice_calculation_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="ipricesnapshotproduct",
            name="effective_approved_rrp_median",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=18,
                null=True,
                verbose_name="Медиана итоговой РРЦ",
            ),
        ),
        migrations.AddField(
            model_name="ipricesnapshotproduct",
            name="current_vs_approved_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=18,
                null=True,
                verbose_name="Разница розницы и итоговой РРЦ",
            ),
        ),
        migrations.RunPython(
            populate_product_approval_summaries,
            migrations.RunPython.noop,
        ),
    ]
