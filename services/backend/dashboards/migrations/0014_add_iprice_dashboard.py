from django.db import migrations, models


def create_iprice_dashboard(apps, schema_editor):
    Dashboard = apps.get_model(
        "dashboards",
        "Dashboard",
    )
    DashboardWidget = apps.get_model(
        "dashboards",
        "DashboardWidget",
    )

    dashboard, _ = Dashboard.objects.update_or_create(
        slug="iprice",
        defaults={
            "name": "IPrice",
        },
    )

    DashboardWidget.objects.get_or_create(
        dashboard=dashboard,
        type="iprice_dashboard",
        defaults={
            "position": 0,
            "config": {},
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0013_alter_dashboardwidget_config_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dashboardwidget",
            name="type",
            field=models.CharField(
                choices=[
                    ("table", "Table"),
                    ("line_chart", "Line Chart"),
                    ("fb_project_gantt", "FB Project Gantt"),
                    ("yd_wordstat_table", "YD Wordstat Table"),
                    ("fb_purchases_dashboard", "FB Purchases Dashboard"),
                    ("fb_turnover_dashboard", "FB Turnover Dashboard"),
                    ("fb_accreceiv_dashboard", "FB Accreceiv Dashboard"),
                    ("planned_sales_dashboard", "Planned Sales Dashboard"),
                    ("revenue_dashboard", "Revenue Dashboard"),
                    ("iprice_dashboard", "iPrice Dashboard"),
                ],
                max_length=50,
            ),
        ),
        migrations.RunPython(
            create_iprice_dashboard,
            migrations.RunPython.noop,
        ),
    ]
