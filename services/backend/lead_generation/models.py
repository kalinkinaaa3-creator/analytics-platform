from django.conf import settings
from django.db import models


class LeadGenerationPlan(models.Model):
    week_start = models.DateField(unique=True, db_index=True)
    budget_vat = models.DecimalField(max_digits=18, decimal_places=2)
    target_lead_price = models.DecimalField(max_digits=18, decimal_places=2)
    target_leads = models.DecimalField(max_digits=18, decimal_places=4)
    revenue_plan = models.DecimalField(max_digits=18, decimal_places=2)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lead_generation_plan"
        ordering = ("week_start",)


class LeadGenerationSourcePreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lead_generation_source_preference")
    source_ids = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lead_generation_source_preference"
