from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "datasets",
            "0055_ipricesnapshot_was_active",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="parserproductmatch",
            name="match_type",
            field=models.CharField(
                choices=[
                    (
                        "manual",
                        "Добавлен вручную",
                    ),
                    (
                        "auto",
                        "Добавлен автоматически",
                    ),
                ],
                db_index=True,
                default="manual",
                max_length=20,
                verbose_name="Способ добавления",
            ),
        ),
    ]
