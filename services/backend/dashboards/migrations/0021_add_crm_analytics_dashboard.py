from django.db import migrations, models


def create_crm_analytics_dashboard(apps, schema_editor):
    dashboard_model = apps.get_model("dashboards", "Dashboard")
    widget_model = apps.get_model("dashboards", "DashboardWidget")
    dashboard, _ = dashboard_model.objects.update_or_create(
        slug="crm-analytics",
        defaults={"name": "Аналитика CRM"},
    )
    widget_model.objects.update_or_create(
        dashboard=dashboard,
        type="crm_analytics_dashboard",
        defaults={"position": 0, "config": {}},
    )


def remove_crm_analytics_dashboard(apps, schema_editor):
    dashboard_model = apps.get_model("dashboards", "Dashboard")
    dashboard_model.objects.filter(slug="crm-analytics").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0020_delete_iprice_sales_region_mapping"),
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
                    ("crm_analytics_dashboard", "CRM Analytics Dashboard"),
                ],
                max_length=50,
            ),
        ),
        migrations.RunPython(
            create_crm_analytics_dashboard,
            remove_crm_analytics_dashboard,
        ),
    ]
