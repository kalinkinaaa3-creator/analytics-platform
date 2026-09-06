from django.conf import settings
from django.db import models
import uuid


class SeoGoal(models.Model):
    external_id = models.BigIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    source_name = models.CharField(max_length=255, blank=True, default="")
    parent_external_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    nesting_level = models.PositiveSmallIntegerField(default=0)
    goal_type = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    is_available = models.BooleanField(default=True, db_index=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_goal"
        ordering = ("position", "id")

    def __str__(self):
        return f"{self.name} ({self.external_id})"


class SeoBrandMask(models.Model):
    mask = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_brand_mask"
        ordering = ("mask",)

    def __str__(self):
        return self.mask


class SeoRefreshRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    class Trigger(models.TextChoices):
        MANUAL = "manual", "Manual"
        SCHEDULED = "scheduled", "Scheduled"
        SYSTEM = "system", "System"

    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.SYSTEM)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seo_refresh_runs",
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "seo_refresh_run"
        ordering = ("-started_at", "-id")


class SeoBackfillCheckpoint(models.Model):
    key = models.CharField(max_length=32, unique=True, default="warehouse")
    status = models.CharField(max_length=16, default="loading")
    date_from = models.DateField()
    date_to = models.DateField()
    completed_through = models.DateField(null=True, blank=True)
    tables = models.JSONField(default=dict)
    configuration = models.JSONField(default=dict)
    stats = models.JSONField(default=dict, blank=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    error = models.TextField(blank=True, default="")
    date_add = models.DateTimeField(auto_now_add=True)
    date_update = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_backfill_checkpoint"


class SeoApiRequestLog(models.Model):
    endpoint = models.CharField(max_length=255)
    report_key = models.CharField(max_length=100, blank=True, default="", db_index=True)
    params = models.JSONField(default=dict, blank=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    sampled = models.BooleanField(null=True, blank=True)
    sample_share = models.FloatField(null=True, blank=True)
    data_lag = models.PositiveIntegerField(null=True, blank=True)
    success = models.BooleanField(default=False, db_index=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "seo_api_request_log"
        ordering = ("-created_at", "-id")


class SeoExportRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING, db_index=True)
    page = models.CharField(max_length=32)
    filters = models.JSONField(default=dict)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="seo_export_runs")
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    file_path = models.CharField(max_length=500, blank=True, default="")
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "seo_export_run"
        ordering = ("-started_at",)
