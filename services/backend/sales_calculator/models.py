from django.conf import settings
from django.db import models


class SalesCalculatorPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    config = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class SalesCalculatorRefresh(models.Model):
    # One shared coordinator for manual refreshes and source completion hooks.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    requested = models.BooleanField(default=False)
    refresh_sources = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="never")
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    price_updated_at = models.DateTimeField(null=True)
    stock_updated_at = models.DateTimeField(null=True)
    stock_failed_at = models.DateTimeField(null=True)
    stock_available = models.BooleanField(default=False)
    error = models.TextField(default="", blank=True)
    row_count = models.PositiveIntegerField(default=0)
