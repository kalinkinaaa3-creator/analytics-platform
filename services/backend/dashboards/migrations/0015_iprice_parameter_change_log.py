from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0014_add_iprice_dashboard"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IPriceParameterChangeLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_id", models.BigIntegerField(db_index=True)),
                ("mode", models.CharField(max_length=20)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("search", models.TextField(blank=True, default="")),
                ("changes", models.JSONField(default=dict)),
                ("affected", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(db_index=True, default="pending", max_length=20)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="iprice_parameter_change_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Changing iPrice settings",
                "verbose_name_plural": "Changing iPrice settings",
                "db_table": "iprice_parameter_change_log",
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
