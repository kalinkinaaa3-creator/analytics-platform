from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bitrix24", "0005_bitrixmanagertracking")]

    operations = [
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="title",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="source_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="opportunity",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=18, null=True
            ),
        ),
    ]
