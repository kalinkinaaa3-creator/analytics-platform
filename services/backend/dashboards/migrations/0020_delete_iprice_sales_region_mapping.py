from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0019_sales_region_mapping_ordering"),
    ]

    operations = [
        migrations.DeleteModel(
            name="IPriceSalesRegionMapping",
        ),
    ]
