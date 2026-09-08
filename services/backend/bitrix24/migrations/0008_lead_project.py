from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bitrix24", "0007_crm_dashboard_rework")]

    operations = [
        migrations.AddField(
            model_name="bitrixlead",
            name="project_id",
            field=models.CharField(max_length=128, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="project_id",
            field=models.CharField(max_length=128, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="project_name",
            field=models.TextField(blank=True, default=""),
        ),
    ]
