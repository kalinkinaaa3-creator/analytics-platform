from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="LeadGenerationPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField(db_index=True, unique=True)),
                ("budget_vat", models.DecimalField(decimal_places=2, max_digits=18)),
                ("target_lead_price", models.DecimalField(decimal_places=2, max_digits=18)),
                ("target_leads", models.DecimalField(decimal_places=4, max_digits=18)),
                ("revenue_plan", models.DecimalField(decimal_places=2, max_digits=18)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "lead_generation_plan", "ordering": ("week_start",)},
        ),
        migrations.CreateModel(
            name="LeadGenerationSourcePreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_ids", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="lead_generation_source_preference", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "lead_generation_source_preference"},
        ),
    ]
