from django.db import migrations, models
from django.db.models import Q


def expand_departure_discounts(apps, schema_editor):
    discount_model = apps.get_model(
        "datasets",
        "DepartureDiscount",
    )
    config_model = apps.get_model(
        "datasets",
        "IPriceCalculationConfig",
    )
    region_model = apps.get_model(
        "datasets",
        "IPriceSnapshotRegion",
    )

    legacy_rows = list(
        discount_model.objects.filter(
            arrival__isnull=True,
        ).order_by("date_add", "id")
    )

    for legacy in legacy_rows:
        arrivals = set(
            config_model.objects.filter(
                product_key=legacy.product_key,
                departure__iexact=legacy.departure,
            ).exclude(
                arrival="",
            ).values_list("arrival", flat=True)
        )
        arrivals.update(
            region_model.objects.filter(
                departure_discount_source_id=legacy.id,
            ).exclude(
                sale_region="",
            ).values_list("sale_region", flat=True)
        )
        arrivals = {
            str(value).strip()
            for value in arrivals
            if str(value or "").strip()
        }

        if legacy.is_active and not arrivals:
            raise RuntimeError(
                "Не удалось определить arrival для активной "
                f"departure_discount id={legacy.id}"
            )

        legacy_was_active = legacy.is_active
        if legacy_was_active:
            discount_model.objects.filter(pk=legacy.pk).update(
                is_active=False,
            )

        for arrival in sorted(arrivals):
            clone = discount_model.objects.create(
                product_key=legacy.product_key,
                departure=legacy.departure,
                arrival=arrival,
                distr=legacy.distr,
                distr_1=legacy.distr_1,
                small=legacy.small,
                medium=legacy.medium,
                large=legacy.large,
                is_active=legacy_was_active,
            )
            discount_model.objects.filter(pk=clone.pk).update(
                date_add=legacy.date_add,
            )


class Migration(migrations.Migration):
    dependencies = [
        (
            "datasets",
            "0052_ipricesnapshotproduct_assortment_matrix_status",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="departurediscount",
            name="arrival",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Для legacy-строк может быть пустым",
                max_length=255,
                null=True,
                verbose_name="Регион продажи",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="departurediscount",
            name="uniq_active_dep_discount_product_departure",
        ),
        migrations.RemoveIndex(
            model_name="departurediscount",
            name="dep_disc_key_active_idx",
        ),
        migrations.RemoveIndex(
            model_name="departurediscount",
            name="dep_disc_key_date_idx",
        ),
        migrations.RunPython(
            expand_departure_discounts,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="departurediscount",
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True),
                fields=("product_key", "departure", "arrival"),
                name="uniq_active_dep_discount_product_route",
            ),
        ),
        migrations.AddConstraint(
            model_name="departurediscount",
            constraint=models.CheckConstraint(
                condition=(
                    Q(is_active=False)
                    | Q(arrival__isnull=False)
                ),
                name="active_dep_discount_requires_arrival",
            ),
        ),
        migrations.AddIndex(
            model_name="departurediscount",
            index=models.Index(
                fields=(
                    "product_key",
                    "departure",
                    "arrival",
                    "is_active",
                ),
                name="dep_disc_route_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="departurediscount",
            index=models.Index(
                fields=(
                    "product_key",
                    "departure",
                    "arrival",
                    "date_add",
                ),
                name="dep_disc_route_date_idx",
            ),
        ),
    ]
