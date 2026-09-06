import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("context_analytics", "0003_context_backfill_checkpoint_configuration"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ContextExportRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failed", "Failed")], db_index=True, default="running", max_length=16)),
                ("page", models.CharField(max_length=32)),
                ("filters", models.JSONField(default=dict)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("file_path", models.CharField(blank=True, default="", max_length=500)),
                ("error", models.TextField(blank=True, default="")),
                ("started_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="context_export_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "context_export_run", "ordering": ("-started_at",)},
        ),
    ]
