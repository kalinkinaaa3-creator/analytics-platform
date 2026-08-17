from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dashboards", "0015_iprice_parameter_change_log"),
    ]

    operations = [
        migrations.CreateModel(
            name="IPricePriceZoneConfig",
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
                    "below_market_threshold",
                    models.DecimalField(
                        decimal_places=6,
                        default=Decimal("-0.03"),
                        max_digits=8,
                        verbose_name="Нижний порог рынка",
                    ),
                ),
                (
                    "above_market_threshold",
                    models.DecimalField(
                        decimal_places=6,
                        default=Decimal("0.03"),
                        max_digits=8,
                        verbose_name="Верхний порог рынка",
                    ),
                ),
                (
                    "critical_threshold",
                    models.DecimalField(
                        decimal_places=6,
                        default=Decimal("0.10"),
                        max_digits=8,
                        verbose_name="Критический порог",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="Активная конфигурация",
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
                        related_name="created_iprice_price_zone_configs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кем создана",
                    ),
                ),
            ],
            options={
                "verbose_name": "iPrice price zone configuration",
                "verbose_name_plural": "iPrice price zone configurations",
                "db_table": "iprice_price_zone_config",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.AddConstraint(
            model_name="ipricepricezoneconfig",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("is_active",),
                name="iprice_one_active_price_zone_config",
            ),
        ),
        migrations.AddConstraint(
            model_name="ipricepricezoneconfig",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("below_market_threshold__lt", 0))
                    & models.Q(("above_market_threshold__gt", 0))
                    & models.Q(("critical_threshold__gt", 0))
                    & models.Q(
                        (
                            "below_market_threshold__lt",
                            models.F("above_market_threshold"),
                        )
                    )
                    & models.Q(
                        (
                            "above_market_threshold__lt",
                            models.F("critical_threshold"),
                        )
                    )
                ),
                name="iprice_price_zone_threshold_order",
            ),
        ),
    ]
