from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "datasets",
            (
                "0048_parserproductclassification_"
                "match_type_and_more"
            ),
        ),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="ipricecalculationconfig",
            name=(
                "iprice_config_minimum_margin_range"
            ),
        ),
        migrations.AddConstraint(
            model_name="ipricecalculationconfig",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(minimum_margin__gte=0)
                    & models.Q(minimum_margin__lt=1)
                ),
                name=(
                    "iprice_config_minimum_margin_range"
                ),
            ),
        ),
    ]
