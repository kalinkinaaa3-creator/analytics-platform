from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "datasets",
            "0051_iprice_product_approval_summary",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="ipricesnapshotproduct",
            name="assortment_matrix_status",
            field=models.TextField(
                blank=True,
                null=True,
                verbose_name="САМ",
            ),
        ),
    ]
