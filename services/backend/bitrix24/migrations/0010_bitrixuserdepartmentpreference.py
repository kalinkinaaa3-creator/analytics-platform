from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("bitrix24", "0009_bitrixdeal_bitrixdealcategory"),
    ]

    operations = [
        migrations.CreateModel(
            name="BitrixUserDepartmentPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("manager_settings", models.JSONField(blank=True, default=list)),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="bitrix_department_preference", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "bitrix24_user_department_preference"},
        ),
    ]
