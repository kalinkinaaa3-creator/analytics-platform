from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0059_analytics_product_manual_property"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IPriceCompetitorSelectionOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_key_base", models.BigIntegerField(db_index=True, verbose_name="Product key нашего товара")),
                ("product_key_competitor", models.BigIntegerField(db_index=True, verbose_name="Product key конкурента")),
                ("selection_mode", models.CharField(choices=[("auto", "Автоматический выбор"), ("include", "Включён вручную"), ("exclude", "Исключён вручную")], db_index=True, default="auto", max_length=20, verbose_name="Режим участия в расчёте")),
                ("reason", models.TextField(blank=True, default="", verbose_name="Причина ручного решения")),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("date_update", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="iprice_competitor_selection_overrides", to=settings.AUTH_USER_MODEL, verbose_name="Кем изменено")),
            ],
            options={
                "db_table": "iprice_competitor_selection_override",
                "verbose_name": "iPrice: ручной выбор конкурента",
                "verbose_name_plural": "iPrice: ручной выбор конкурентов",
            },
        ),
        migrations.AddConstraint(
            model_name="ipricecompetitorselectionoverride",
            constraint=models.UniqueConstraint(fields=("product_key_base", "product_key_competitor"), name="iprice_competitor_selection_pair_uniq"),
        ),
        migrations.AddIndex(
            model_name="ipricecompetitorselectionoverride",
            index=models.Index(fields=["product_key_base", "selection_mode"], name="iprice_comp_sel_base_mode_idx"),
        ),
        migrations.CreateModel(
            name="IPriceCompetitorSelectionChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_mode", models.CharField(blank=True, default="", max_length=20)),
                ("selection_mode", models.CharField(choices=[("auto", "Автоматический выбор"), ("include", "Включён вручную"), ("exclude", "Исключён вручную")], max_length=20)),
                ("reason", models.TextField(blank=True, default="")),
                ("date_add", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="iprice_competitor_selection_changes", to=settings.AUTH_USER_MODEL)),
                ("override", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="changes", to="datasets.ipricecompetitorselectionoverride", verbose_name="Настройка конкурента")),
                ("snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="competitor_selection_changes", to="datasets.ipricesnapshot", verbose_name="Снапшот")),
            ],
            options={
                "db_table": "iprice_competitor_selection_change",
                "ordering": ("-date_add", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="ipricecompetitorselectionchange",
            index=models.Index(fields=["snapshot", "date_add"], name="iprice_comp_change_snap_idx"),
        ),
    ]
