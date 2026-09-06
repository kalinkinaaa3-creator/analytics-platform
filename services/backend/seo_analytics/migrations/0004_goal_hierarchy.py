from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("seo_analytics", "0003_remove_report_snapshot")]

    operations = [
        migrations.AddField(
            model_name="seogoal",
            name="parent_external_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="seogoal",
            name="nesting_level",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="seogoal",
            name="goal_type",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
