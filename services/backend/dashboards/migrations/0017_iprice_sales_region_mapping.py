from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.comparison
import django.db.models.functions.text


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dashboards", "0016_iprice_price_zone_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="IPriceSalesRegionMapping",
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
                (
                    "region",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        verbose_name="Регион продажи",
                    ),
                ),
                (
                    "partner_inn",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        verbose_name="ИНН партнёра",
                    ),
                ),
                (
                    "shipp_region",
                    models.CharField(
                        db_index=True,
                        max_length=255,
                        verbose_name="Аналитический регион",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="Активное соответствие",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        verbose_name="Дата создания",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_iprice_sales_region_mappings",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кем создано",
                    ),
                ),
            ],
            options={
                "verbose_name": "iPrice sales region mapping",
                "verbose_name_plural": "iPrice sales region mappings",
                "db_table": "iprice_sales_region_mapping",
                "ordering": (
                    "shipp_region",
                    "region",
                    "partner_inn",
                    "-id",
                ),
            },
        ),
        migrations.AddConstraint(
            model_name="ipricesalesregionmapping",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("region__isnull", False))
                    & ~models.Q(("region", ""))
                    | models.Q(("partner_inn__isnull", False))
                    & ~models.Q(("partner_inn", ""))
                ),
                name="iprice_sales_region_mapping_has_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="ipricesalesregionmapping",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.comparison.Coalesce(
                        "region",
                        models.Value(""),
                    )
                ),
                django.db.models.functions.comparison.Coalesce(
                    "partner_inn",
                    models.Value(""),
                ),
                condition=models.Q(("is_active", True)),
                name="iprice_unique_active_sales_region_source",
            ),
        ),
        migrations.AddIndex(
            model_name="ipricesalesregionmapping",
            index=models.Index(
                fields=["region", "is_active"],
                name="iprice_sales_region_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ipricesalesregionmapping",
            index=models.Index(
                fields=["partner_inn", "is_active"],
                name="iprice_sales_inn_active_idx",
            ),
        ),
    ]
