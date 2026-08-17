from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0018_sales_region_mapping_region_code"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="ipricesalesregionmapping",
            options={
                "ordering": (
                    "shipp_region",
                    "region",
                    "partner_region_code",
                    "-id",
                ),
                "verbose_name": "iPrice sales region mapping",
                "verbose_name_plural": "iPrice sales region mappings",
            },
        ),
    ]
