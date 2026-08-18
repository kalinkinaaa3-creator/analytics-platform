import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bitrix24", "0004_initial_status_map"),
    ]

    operations = [
        migrations.CreateModel(
            name="BitrixManagerTracking",
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
                ("user_id", models.BigIntegerField(unique=True)),
                ("manager_name", models.CharField(max_length=767)),
                ("is_tracked", models.BooleanField(db_index=True, default=True)),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="manager_tracking_rows",
                        to="bitrix24.bitrixdepartment",
                    ),
                ),
            ],
            options={
                "db_table": "bitrix24_manager_tracking",
                "ordering": ("manager_name", "user_id"),
            },
        ),
    ]
