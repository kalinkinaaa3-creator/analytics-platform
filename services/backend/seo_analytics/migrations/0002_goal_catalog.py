from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("seo_analytics", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="seogoal",
            name="is_available",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="seogoal",
            name="source_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="seogoal",
            name="source_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
