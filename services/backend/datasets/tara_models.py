"""Durable execution state; session secrets live in a private Docker volume."""
from django.conf import settings
from django.db import models


class TaraRun(models.Model):
    ACTIVE = ("queued", "dispatching", "running", "waiting_session")
    origin = models.CharField(max_length=16, default="cli")
    request_key = models.CharField(max_length=255, unique=True)
    master = models.ForeignKey("datasets.ParserMasterPipelineRun", null=True,
                               blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=24, default="queued", db_index=True)
    options = models.JSONField(default=dict)
    phase = models.CharField(max_length=24, default="products")
    session = models.ForeignKey("datasets.TaraSession", null=True, blank=True,
                                on_delete=models.PROTECT, related_name="executions")
    error = models.TextField(blank=True, default="")
    wait_until = models.DateTimeField(null=True, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    resume_at = models.DateTimeField(null=True, blank=True)
    lease = models.CharField(max_length=64, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TaraItem(models.Model):
    run = models.ForeignKey(TaraRun, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("datasets.ParserProductUrl", on_delete=models.PROTECT)
    status = models.CharField(max_length=24, default="pending", db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("run", "product"), name="tara_run_product_unique")]


class TaraSession(models.Model):
    run = models.ForeignKey(TaraRun, on_delete=models.PROTECT, related_name="uploads")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL)
    status = models.CharField(max_length=24, default="pending", db_index=True)
    filename = models.CharField(max_length=80, unique=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    checked_at = models.DateTimeField(null=True, blank=True)


class TaraCoordinator(models.Model):
    """One row serializes dispatch/upload transitions, not product requests."""
    key = models.PositiveSmallIntegerField(primary_key=True, default=1)
