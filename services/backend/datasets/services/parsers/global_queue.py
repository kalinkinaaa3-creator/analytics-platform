"""Durable FIFO admission; waiting for a remote executor retains capacity.

No automatic expiry/reassignment: a missing heartbeat does not prove that an
executor stopped. Integration must release only after all child work has ended.
"""
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from datasets.parser_queue_models import ParserQueueCoordinator, ParserQueueEntry
from datasets.services.iprice_workspace import workspace_for


class QueueOwnershipError(RuntimeError):
    pass


def _lock():
    ParserQueueCoordinator.objects.get_or_create(pk=1)
    return ParserQueueCoordinator.objects.select_for_update().get(pk=1)


def enqueue(*, organization, kind, run_id):
    workspace_for(organization)
    if kind not in {"master", "tara", "base", "ps", "tt", "links", "images"}:
        raise ValueError("Unknown parser job kind")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise ValueError("A persisted positive run ID is required")
    key = f"{organization.pk}:{kind}:{run_id}"
    with transaction.atomic():
        _lock()
        entry, _ = ParserQueueEntry.objects.get_or_create(request_key=key, defaults={
            "organization": organization, "kind": kind, "run_id": run_id,
        })
        return entry


def claim_next(*, executor, entry_id=None):
    """Exactly one claimant receives the token, including duplicate dispatchers."""
    if not executor or len(executor) > 200:
        raise ValueError("Executor identity is required")
    with transaction.atomic():
        _lock()
        if ParserQueueEntry.objects.filter(status__in=ParserQueueEntry.OCCUPIED).exists():
            return None
        entry = ParserQueueEntry.objects.select_for_update().filter(status="queued").order_by("id").first()
        if entry is None:
            return None
        if entry_id is not None and entry.pk != entry_id:
            return None
        now = timezone.now()
        entry.status, entry.token, entry.executor = "running", uuid4().hex, executor
        entry.started_at = entry.heartbeat_at = now
        entry.save(update_fields=["status", "token", "executor", "started_at", "heartbeat_at"])
        return entry


def _owned(entry_id, token):
    entry = ParserQueueEntry.objects.select_for_update().get(pk=entry_id)
    if not token or entry.token != token or entry.status not in ParserQueueEntry.OCCUPIED:
        raise QueueOwnershipError("Parser queue ownership is no longer valid")
    return entry


def heartbeat(entry_id, token):
    with transaction.atomic():
        entry = _owned(entry_id, token)
        # A late heartbeat does not silently clear recovery_required.
        entry.heartbeat_at = timezone.now()
        entry.save(update_fields=["heartbeat_at"])


def wait_for_remote(entry_id, token, *, message):
    with transaction.atomic():
        entry = _owned(entry_id, token)
        if entry.status != "running":
            raise QueueOwnershipError("Only a running owner may hand off to a remote executor")
        entry.status, entry.message = "waiting_remote", message
        entry.heartbeat_at = timezone.now()
        entry.save(update_fields=["status", "message", "heartbeat_at"])


def resume(entry_id, token, *, executor):
    """Transfer ownership after remote work has finished; old callbacks are fenced."""
    if not executor or len(executor) > 200:
        raise ValueError("Executor identity is required")
    with transaction.atomic():
        _lock()
        entry = _owned(entry_id, token)
        if entry.status != "waiting_remote":
            raise QueueOwnershipError("Job is not waiting for remote completion")
        entry.status, entry.token, entry.executor = "running", uuid4().hex, executor
        entry.heartbeat_at, entry.message = timezone.now(), ""
        entry.save(update_fields=["status", "token", "executor", "heartbeat_at", "message"])
        return entry


def finish(entry_id, token, *, success, message=""):
    """Caller must first join/stop all child requests; never release on a timer."""
    with transaction.atomic():
        _lock()
        entry = _owned(entry_id, token)
        if entry.status != "running":
            raise QueueOwnershipError("Remote/recovery work must be resolved before releasing capacity")
        entry.status = "success" if success else "failed"
        entry.message, entry.finished_at, entry.token = message, timezone.now(), ""
        entry.save(update_fields=["status", "message", "finished_at", "token"])


def cancel_queued(entry_id, *, organization):
    with transaction.atomic():
        _lock()
        entry = ParserQueueEntry.objects.select_for_update().get(pk=entry_id, organization=organization)
        if entry.status != "queued":
            raise QueueOwnershipError("A running parser cannot be cancelled by releasing its slot")
        entry.status, entry.finished_at = "cancelled", timezone.now()
        entry.save(update_fields=["status", "finished_at"])


def flag_stalled(*, timeout=timedelta(minutes=10)):
    """Fail closed: stalled work remains the owner until investigated."""
    with transaction.atomic():
        _lock()
        return ParserQueueEntry.objects.filter(status="running", heartbeat_at__lt=timezone.now() - timeout).update(
            status="recovery_required", message="Исполнитель не отвечает. Требуется проверка завершения процесса.")


def queue_status(*, organization):
    """Expose only this organization's jobs; never disclose another tenant's data."""
    own = ParserQueueEntry.objects.filter(organization=organization).exclude(status__in=ParserQueueEntry.TERMINAL)
    occupied = ParserQueueEntry.objects.filter(status__in=ParserQueueEntry.OCCUPIED)
    result = []
    for entry in own.order_by("id"):
        ahead = ParserQueueEntry.objects.filter(status="queued", id__lt=entry.pk).count() if entry.status == "queued" else 0
        result.append({"id": entry.pk, "kind": entry.kind, "run_id": entry.run_id, "status": entry.status,
                       "position": ahead + 1 if entry.status == "queued" else None,
                       "waiting_for_capacity": entry.status == "queued" and occupied.exists(),
                       "message": entry.message})
    return result
