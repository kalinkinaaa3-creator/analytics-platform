from django.db import migrations, models


def populate_configuration(apps, schema_editor):
    Checkpoint = apps.get_model("context_analytics", "ContextBackfillCheckpoint")
    Goal = apps.get_model("seo_analytics", "SeoGoal")
    goal_ids = list(
        Goal.objects.filter(is_available=True)
        .order_by("external_id")
        .values_list("external_id", flat=True)
    )
    Checkpoint.objects.update(configuration={"goal_ids": goal_ids})


class Migration(migrations.Migration):
    dependencies = [
        ("context_analytics", "0002_context_backfill_checkpoint"),
        ("seo_analytics", "0004_goal_hierarchy"),
    ]

    operations = [
        migrations.AddField(
            model_name="contextbackfillcheckpoint",
            name="configuration",
            field=models.JSONField(default=dict),
        ),
        migrations.RunPython(populate_configuration, migrations.RunPython.noop),
    ]
