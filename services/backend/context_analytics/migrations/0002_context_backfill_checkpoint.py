from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("context_analytics", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ContextBackfillCheckpoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="initial", max_length=32, unique=True)),
                ("status", models.CharField(default="loading", max_length=16)),
                ("date_from", models.DateField()),
                ("date_to", models.DateField()),
                ("completed_through", models.DateField(blank=True, null=True)),
                ("tables", models.JSONField(default=dict)),
                ("stats", models.JSONField(blank=True, default=dict)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("error", models.TextField(blank=True, default="")),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "context_backfill_checkpoint"},
        ),
    ]
