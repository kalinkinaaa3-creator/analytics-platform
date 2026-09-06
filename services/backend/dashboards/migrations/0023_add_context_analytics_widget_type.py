from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboards", "0022_add_seo_analytics_widget_type")]
    operations = [
        migrations.AlterField(
            model_name="dashboardwidget",
            name="type",
            field=models.CharField(max_length=50, choices=[
                ("table", "Table"), ("line_chart", "Line Chart"),
                ("fb_project_gantt", "FB Project Gantt"), ("yd_wordstat_table", "YD Wordstat Table"),
                ("fb_purchases_dashboard", "FB Purchases Dashboard"),
                ("fb_turnover_dashboard", "FB Turnover Dashboard"),
                ("fb_accreceiv_dashboard", "FB Accreceiv Dashboard"),
                ("planned_sales_dashboard", "Planned Sales Dashboard"),
                ("revenue_dashboard", "Revenue Dashboard"), ("iprice_dashboard", "iPrice Dashboard"),
                ("crm_analytics_dashboard", "CRM Analytics Dashboard"),
                ("seo_analytics_dashboard", "SEO Analytics Dashboard"),
                ("context_analytics_dashboard", "Context Analytics Dashboard"),
            ]),
        ),
    ]
