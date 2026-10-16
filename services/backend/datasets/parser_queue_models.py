"""Shared capacity for parser jobs from both organizations."""
from django.db import models


class ParserQueueCoordinator(models.Model):
    key = models.PositiveSmallIntegerField(primary_key=True, default=1)

    class Meta:
        db_table = "parser_queue_coordinator"


class ParserQueueEntry(models.Model):
    OCCUPIED = ("running", "waiting_remote", "recovery_required")
    TERMINAL = ("success", "failed", "cancelled")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    request_key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=24)
    run_id = models.PositiveBigIntegerField()
    status = models.CharField(max_length=24, default="queued", db_index=True)
    resource = models.CharField(max_length=32, default="iprice-parsers", editable=False)
    token = models.CharField(max_length=64, blank=True, default="")
    executor = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    recovery_audit = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "parser_queue_entry"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["resource"], condition=models.Q(status__in=("running", "waiting_remote", "recovery_required")), name="parser_queue_single_occupied"),
            models.CheckConstraint(condition=models.Q(status__in=("queued", "running", "waiting_remote", "recovery_required", "success", "failed", "cancelled")), name="parser_queue_valid_status"),
            models.CheckConstraint(condition=models.Q(resource="iprice-parsers"), name="parser_queue_fixed_resource"),
        ]
