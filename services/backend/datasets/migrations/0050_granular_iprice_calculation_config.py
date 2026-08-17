from django.db import migrations, models
from django.db.models import Q


def clear_legacy_configs(apps, schema_editor):
    config_model = apps.get_model(
        "datasets",
        "IPriceCalculationConfig",
    )
    config_model.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0049_allow_zero_iprice_minimum_margin"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="ipricecalculationconfig",
            name="unique_active_iprice_config_per_item_type",
        ),
        migrations.RunPython(
            clear_legacy_configs,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="ipricecalculationconfig",
            name="item_type",
        ),
        migrations.AddField(
            model_name="ipricecalculationconfig",
            name="product_key",
            field=models.BigIntegerField(
                db_index=True,
                verbose_name="Product key",
            ),
        ),
        migrations.AddField(
            model_name="ipricecalculationconfig",
            name="departure",
            field=models.CharField(
                db_index=True,
                max_length=255,
                verbose_name="Место производства",
            ),
        ),
        migrations.AddField(
            model_name="ipricecalculationconfig",
            name="arrival",
            field=models.CharField(
                db_index=True,
                max_length=255,
                verbose_name="Регион продажи",
            ),
        ),
        migrations.AlterModelOptions(
            name="ipricecalculationconfig",
            options={
                "ordering": (
                    "product_key",
                    "departure",
                    "arrival",
                    "-date_add",
                    "-id",
                ),
                "verbose_name": "Конфигурация расчета iPrice",
                "verbose_name_plural": "Конфигурации расчета iPrice",
            },
        ),
        migrations.AddConstraint(
            model_name="ipricecalculationconfig",
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True),
                fields=("product_key", "departure", "arrival"),
                name="unique_active_iprice_config_per_product_route",
            ),
        ),
        migrations.AddIndex(
            model_name="ipricecalculationconfig",
            index=models.Index(
                fields=(
                    "product_key",
                    "departure",
                    "arrival",
                    "date_add",
                ),
                name="iprice_config_route_date_idx",
            ),
        ),
    ]
