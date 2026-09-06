import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed(apps, schema_editor):
    Dashboard = apps.get_model("dashboards", "Dashboard")
    Widget = apps.get_model("dashboards", "DashboardWidget")
    dashboard, _ = Dashboard.objects.update_or_create(slug="context-analytics", defaults={"name": "Контекстная реклама"})
    Widget.objects.update_or_create(dashboard=dashboard, type="context_analytics_dashboard",
                                    defaults={"position": 0, "config": {}})


def unseed(apps, schema_editor):
    apps.get_model("dashboards", "Dashboard").objects.filter(slug="context-analytics").delete()


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL),
                    ("dashboards", "0023_add_context_analytics_widget_type")]
    operations = [
        migrations.CreateModel(name="ContextCampaign", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("external_id", models.BigIntegerField(db_index=True, unique=True)), ("name", models.CharField(max_length=255)),
            ("campaign_type", models.CharField(blank=True, db_index=True, default="", max_length=64)),
            ("status", models.CharField(blank=True, default="", max_length=64)),
            ("state", models.CharField(blank=True, default="", max_length=64)),
            ("start_date", models.DateField(blank=True, null=True)),
            ("is_available", models.BooleanField(db_index=True, default=True)),
            ("source_updated_at", models.DateTimeField(blank=True, null=True)),
            ("date_add", models.DateTimeField(auto_now_add=True)), ("date_update", models.DateTimeField(auto_now=True)),
        ], options={"db_table": "context_campaign", "ordering": ("name", "external_id")}),
        migrations.CreateModel(name="ContextApiRequestLog", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("endpoint", models.CharField(max_length=255)), ("report_key", models.CharField(blank=True, db_index=True, default="", max_length=100)),
            ("params", models.JSONField(blank=True, default=dict)), ("status_code", models.PositiveIntegerField(blank=True, null=True)),
            ("duration_ms", models.PositiveIntegerField(default=0)), ("success", models.BooleanField(db_index=True, default=False)),
            ("error", models.TextField(blank=True, default="")), ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
        ], options={"db_table": "context_api_request_log", "ordering": ("-created_at", "-id")}),
        migrations.CreateModel(name="ContextRefreshRun", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("status", models.CharField(choices=[("running","Running"),("success","Success"),("failed","Failed")], db_index=True, max_length=16)),
            ("trigger", models.CharField(choices=[("manual","Manual"),("scheduled","Scheduled"),("system","System")], default="system", max_length=16)),
            ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)), ("finished_at", models.DateTimeField(blank=True, null=True)),
            ("heartbeat_at", models.DateTimeField(blank=True, null=True)), ("stats", models.JSONField(blank=True, default=dict)),
            ("error", models.TextField(blank=True, default="")),
            ("started_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                             related_name="context_refresh_runs", to=settings.AUTH_USER_MODEL)),
        ], options={"db_table": "context_refresh_run", "ordering": ("-started_at", "-id")}),
        migrations.RunPython(seed, unseed),
    ]
