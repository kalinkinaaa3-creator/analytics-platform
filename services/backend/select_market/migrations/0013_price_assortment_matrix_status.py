from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("select_market", "0012_archive_legacy_routes")]
    operations = [
        migrations.AddField(
            model_name="nomenclatureprice",
            name="assortment_matrix_status",
            field=models.TextField(null=True, blank=True, verbose_name="САМ"),
        ),
    ]
