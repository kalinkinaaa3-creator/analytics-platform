from django.db import migrations, models


def name_from_departments(apps, schema_editor):
    Group = apps.get_model("dashboards", "DashboardDepartmentGroup")
    for group in Group.objects.using(schema_editor.connection.alias).iterator():
        group.name = "; ".join(dict.fromkeys(group.departments))
        group.save(using=schema_editor.connection.alias, update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [("dashboards", "0028_department_dashboard_groups")]
    operations = [
        migrations.AlterModelOptions(name="dashboarddepartmentgroup", options={
            "ordering": ("name", "pk"), "verbose_name": "Group access", "verbose_name_plural": "Groups accesses",
        }),
        migrations.AlterField("dashboarddepartmentgroup", "name", models.TextField("Name", blank=True)),
        migrations.AlterField("dashboarddepartmentgroup", "can_view", models.BooleanField("Can view", default=True)),
        migrations.AlterField("dashboarddepartmentgroup", "can_edit", models.BooleanField("Can edit", default=False)),
        migrations.AlterField("dashboarddepartmentgroup", "is_active", models.BooleanField("Active", default=True)),
        migrations.RunPython(name_from_departments, migrations.RunPython.noop),
    ]
