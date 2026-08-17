from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("datasets", "0058_analytics_product_match_candidate_application"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalyticsProductManualProperty",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("product_key", models.BigIntegerField(db_index=True)),
                ("property_name", models.CharField(db_index=True, max_length=100)),
                ("value", models.TextField()),
                ("date_add", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "analytics_product_manual_property",
            },
        ),
        migrations.AddConstraint(
            model_name="analyticsproductmanualproperty",
            constraint=models.UniqueConstraint(
                fields=("product_key", "property_name"),
                name="analytics_manual_property_product_name_uniq",
            ),
        ),
    ]
