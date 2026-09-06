from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("seo_analytics", "0004_goal_hierarchy")]

    operations = [
        migrations.CreateModel(
            name="SeoBackfillCheckpoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="warehouse", max_length=32, unique=True)),
                ("status", models.CharField(default="loading", max_length=16)),
                ("date_from", models.DateField()),
                ("date_to", models.DateField()),
                ("completed_through", models.DateField(blank=True, null=True)),
                ("tables", models.JSONField(default=dict)),
                ("configuration", models.JSONField(default=dict)),
                ("stats", models.JSONField(blank=True, default=dict)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("error", models.TextField(blank=True, default="")),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "seo_backfill_checkpoint"},
        ),
    ]
