from django.db import migrations, models
from django.db.models.functions import Coalesce, Lower


def normalize_region_codes(apps, schema_editor):
    mapping = apps.get_model("dashboards", "IPriceSalesRegionMapping")
    for item in (
        mapping.objects
        .exclude(partner_region_code__isnull=True)
        .order_by()
    ):
        digits = "".join(
            char for char in (item.partner_region_code or "") if char.isdigit()
        )
        normalized = digits[:2] or None
        if item.partner_region_code != normalized:
            item.partner_region_code = normalized
            item.save(update_fields=("partner_region_code",))

    seen = set()
    for item in mapping.objects.filter(is_active=True).order_by("-id"):
        key = (
            (item.region or "").casefold(),
            item.partner_region_code or "",
        )
        if key in seen:
            item.is_active = False
            item.save(update_fields=("is_active",))
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0017_iprice_sales_region_mapping"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="ipricesalesregionmapping",
            name="iprice_sales_region_mapping_has_source",
        ),
        migrations.RemoveConstraint(
            model_name="ipricesalesregionmapping",
            name="iprice_unique_active_sales_region_source",
        ),
        migrations.RemoveIndex(
            model_name="ipricesalesregionmapping",
            name="iprice_sales_inn_active_idx",
        ),
        migrations.RenameField(
            model_name="ipricesalesregionmapping",
            old_name="partner_inn",
            new_name="partner_region_code",
        ),
        migrations.RunPython(
            normalize_region_codes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="ipricesalesregionmapping",
            name="partner_region_code",
            field=models.CharField(
                blank=True,
                max_length=2,
                null=True,
                verbose_name="Код региона партнёра",
            ),
        ),
        migrations.AddConstraint(
            model_name="ipricesalesregionmapping",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(region__isnull=False) & ~models.Q(region=""))
                    | (
                        models.Q(partner_region_code__isnull=False)
                        & ~models.Q(partner_region_code="")
                    )
                ),
                name="iprice_sales_region_mapping_has_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="ipricesalesregionmapping",
            constraint=models.UniqueConstraint(
                Lower(Coalesce("region", models.Value(""))),
                Coalesce("partner_region_code", models.Value("")),
                condition=models.Q(is_active=True),
                name="iprice_unique_active_sales_region_source",
            ),
        ),
        migrations.AddIndex(
            model_name="ipricesalesregionmapping",
            index=models.Index(
                fields=["partner_region_code", "is_active"],
                name="iprice_sales_code_active_idx",
            ),
        ),
    ]
