from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("seo_analytics", "0002_goal_catalog")]

    operations = [
        migrations.DeleteModel(name="SeoReportSnapshot"),
    ]
