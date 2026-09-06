import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_seo_configuration(apps, schema_editor):
    goal_model = apps.get_model("seo_analytics", "SeoGoal")
    dashboard_model = apps.get_model("dashboards", "Dashboard")
    widget_model = apps.get_model("dashboards", "DashboardWidget")

    for position, external_id, name in (
        (10, 500791856, "Формы с сайта"),
        (20, 234432026, "КЦ — Все целевые действия"),
    ):
        goal_model.objects.update_or_create(
            external_id=external_id,
            defaults={"name": name, "position": position, "is_active": True},
        )

    dashboard, _ = dashboard_model.objects.update_or_create(
        slug="seo-analytics",
        defaults={"name": "SEO-аналитика"},
    )
    widget_model.objects.update_or_create(
        dashboard=dashboard,
        type="seo_analytics_dashboard",
        defaults={"position": 0, "config": {}},
    )


def remove_seo_configuration(apps, schema_editor):
    dashboard_model = apps.get_model("dashboards", "Dashboard")
    dashboard_model.objects.filter(slug="seo-analytics").delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dashboards", "0022_add_seo_analytics_widget_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="SeoApiRequestLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.CharField(max_length=255)),
                ("report_key", models.CharField(blank=True, db_index=True, default="", max_length=100)),
                ("params", models.JSONField(blank=True, default=dict)),
                ("status_code", models.PositiveIntegerField(blank=True, null=True)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("sampled", models.BooleanField(blank=True, null=True)),
                ("sample_share", models.FloatField(blank=True, null=True)),
                ("data_lag", models.PositiveIntegerField(blank=True, null=True)),
                ("success", models.BooleanField(db_index=True, default=False)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"db_table": "seo_api_request_log", "ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="SeoBrandMask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mask", models.CharField(max_length=255, unique=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "seo_brand_mask", "ordering": ("mask",)},
        ),
        migrations.CreateModel(
            name="SeoGoal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.BigIntegerField(db_index=True, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "seo_goal", "ordering": ("position", "id")},
        ),
        migrations.CreateModel(
            name="SeoRefreshRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failed", "Failed")], db_index=True, max_length=16)),
                ("trigger", models.CharField(choices=[("manual", "Manual"), ("scheduled", "Scheduled"), ("system", "System")], default="system", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("stats", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True, default="")),
                ("started_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seo_refresh_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "seo_refresh_run", "ordering": ("-started_at", "-id")},
        ),
        migrations.CreateModel(
            name="SeoReportSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page", models.CharField(db_index=True, max_length=64)),
                ("filters_hash", models.CharField(db_index=True, max_length=64)),
                ("filters", models.JSONField(default=dict)),
                ("payload", models.JSONField(default=dict)),
                ("source_updated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"db_table": "seo_report_snapshot"},
        ),
        migrations.AddConstraint(
            model_name="seoreportsnapshot",
            constraint=models.UniqueConstraint(fields=("page", "filters_hash"), name="seo_report_snapshot_page_filters_uniq"),
        ),
        migrations.RunPython(seed_seo_configuration, remove_seo_configuration),
    ]
