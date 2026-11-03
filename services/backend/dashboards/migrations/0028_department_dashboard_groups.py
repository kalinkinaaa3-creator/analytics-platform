from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def preserve_manual_access(apps, schema_editor):
    Access = apps.get_model("dashboards", "DashboardAccess")
    Access.objects.using(schema_editor.connection.alias).update(
        manual_can_view=models.F("can_view"), manual_can_edit=models.F("can_edit"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0027_select_market_home"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField("dashboardaccess", "manual_can_view", models.BooleanField(editable=False, null=True)),
        migrations.AddField("dashboardaccess", "manual_can_edit", models.BooleanField(editable=False, null=True)),
        migrations.AddField("dashboardaccess", "from_department_group", models.BooleanField(default=False, editable=False)),
        migrations.RunPython(preserve_manual_access, migrations.RunPython.noop),
        migrations.CreateModel(
            name="DashboardDepartmentGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название группы")),
                ("departments", models.JSONField(default=list, verbose_name="Department name")),
                ("can_view", models.BooleanField(default=True, verbose_name="Право на просмотр")),
                ("can_edit", models.BooleanField(default=False, verbose_name="Право на редактирование")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активна")),
                ("dashboard", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="dashboards.dashboard", verbose_name="Dashboard")),
            ],
            options={"verbose_name": "Group", "verbose_name_plural": "Groups", "ordering": ("name", "pk")},
        ),
        migrations.CreateModel(
            name="DashboardDepartmentExclusion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("dashboard", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="dashboards.dashboard")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "dashboard"), name="dashboard_department_exclusion_unique")]},
        ),
    ]
