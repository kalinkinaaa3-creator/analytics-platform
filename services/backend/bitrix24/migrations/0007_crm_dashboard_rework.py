from django.db import migrations, models


def copy_manual_departments(apps, schema_editor):
    tracking = apps.get_model("bitrix24", "BitrixManagerTracking")
    for row in tracking.objects.select_related("department").iterator(chunk_size=500):
        row.department_name = row.department.name
        row.save(update_fields=("department_name",))


class Migration(migrations.Migration):
    dependencies = [("bitrix24", "0006_lead_analytics_display_fields")]

    operations = [
        migrations.AddField(
            model_name="bitrixmanagertracking",
            name="department_name",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.RunPython(copy_manual_departments, migrations.RunPython.noop),
        migrations.RemoveField(model_name="bitrixmanagertracking", name="department"),
        migrations.RemoveField(model_name="bitrixmanagertracking", name="is_tracked"),
        migrations.AddField(
            model_name="bitrixlead",
            name="activity_event_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="activity_name",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="company_name",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="is_return_customer",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="last_activity_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bitrixleadanalytics",
            name="status_semantic_id",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.DeleteModel(name="BitrixDashboardStatusMap"),
    ]
