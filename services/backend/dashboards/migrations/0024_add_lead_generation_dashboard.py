from django.db import migrations, models


def create_dashboard(apps, schema_editor):
    Dashboard = apps.get_model("dashboards", "Dashboard")
    DashboardWidget = apps.get_model("dashboards", "DashboardWidget")
    dashboard, _ = Dashboard.objects.get_or_create(name="Лидогенерация", defaults={"slug": "lead-generation"})
    if dashboard.slug != "lead-generation":
        dashboard.slug = "lead-generation"
        dashboard.save(update_fields=("slug",))
    DashboardWidget.objects.get_or_create(dashboard=dashboard, type="lead_generation_dashboard", defaults={"position": 0, "config": {}})


def remove_dashboard(apps, schema_editor):
    apps.get_model("dashboards", "Dashboard").objects.filter(slug="lead-generation").delete()


class Migration(migrations.Migration):
    dependencies = [("dashboards", "0023_add_context_analytics_widget_type")]
    operations = [
        migrations.AlterField(
            model_name="dashboardwidget", name="type",
            field=models.CharField(max_length=50, choices=[
                ("table", "Table"), ("line_chart", "Line Chart"),
                ("fb_project_gantt", "FB Project Gantt"), ("yd_wordstat_table", "YD Wordstat Table"),
                ("fb_purchases_dashboard", "FB Purchases Dashboard"), ("fb_turnover_dashboard", "FB Turnover Dashboard"),
                ("fb_accreceiv_dashboard", "FB Accreceiv Dashboard"), ("planned_sales_dashboard", "Planned Sales Dashboard"),
                ("revenue_dashboard", "Revenue Dashboard"), ("iprice_dashboard", "iPrice Dashboard"),
                ("crm_analytics_dashboard", "CRM Analytics Dashboard"), ("seo_analytics_dashboard", "SEO Analytics Dashboard"),
                ("context_analytics_dashboard", "Context Analytics Dashboard"), ("lead_generation_dashboard", "Lead Generation Dashboard"),
            ]),
        ),
        migrations.RunPython(create_dashboard, remove_dashboard),
    ]
