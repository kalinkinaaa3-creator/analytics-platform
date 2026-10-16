"""Operator recovery after verified shutdown, never an automatic timeout unlock."""
from hashlib import sha256
import json

from django.db import transaction
from django.utils import timezone

from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.iprice_workspace import workspace_for
from .global_queue import QueueOwnershipError, _lock


def fingerprint(entry):
    values = [entry.pk, entry.status, entry.token, entry.executor,
              entry.heartbeat_at.isoformat() if entry.heartbeat_at else None]
    return sha256(json.dumps(values).encode()).hexdigest()


def inspect_entry(entry_id):
    entry = ParserQueueEntry.objects.select_related("organization").get(pk=entry_id)
    return {"id": entry.pk, "organization": entry.organization.code, "kind": entry.kind,
            "run_id": entry.run_id, "status": entry.status, "executor": entry.executor,
            "heartbeat_at": entry.heartbeat_at.isoformat() if entry.heartbeat_at else None,
            "fingerprint": fingerprint(entry), "recovery_audit": entry.recovery_audit}


def recover_stopped(entry_id, *, expected_fingerprint, operator, reason, workers_confirmed_stopped):
    if not workers_confirmed_stopped or not operator.strip() or len(reason.strip()) < 10:
        raise ValueError("Confirm all workers stopped; operator and a specific reason are required")
    with transaction.atomic():
        _lock()
        entry = ParserQueueEntry.objects.select_for_update().select_related("organization").get(pk=entry_id)
        if entry.status not in ParserQueueEntry.OCCUPIED or fingerprint(entry) != expected_fingerprint:
            raise QueueOwnershipError("State changed after inspection; inspect again before recovery")
        workspace = workspace_for(entry.organization)
        now = timezone.now()
        message = "Остановлено оператором при восстановлении общей очереди: " + reason.strip()
        runs = workspace.model("TaraRun").objects.none()
        if entry.kind == "master":
            workspace.model("ParserMasterPipelineRun").objects.filter(pk=entry.run_id).exclude(status__in=("success", "failed", "cancelled")).update(
                status="failed", finished_at=now, error=message)
            runs = workspace.model("TaraRun").objects.filter(master_id=entry.run_id)
        elif entry.kind == "tara":
            runs = workspace.model("TaraRun").objects.filter(pk=entry.run_id)
        ids = list(runs.values_list("id", flat=True))
        if ids:
            workspace.model("TaraFetch").objects.filter(run_id__in=ids).update(status="expired", token="", payload={})
            runs.exclude(status__in=("success", "failed", "cancelled")).update(status="failed", lease="", finished_at=now, error=message)
            # Fence even callbacks from already-cancelled tasks.
            runs.update(lease="")
        entry.recovery_audit = [*entry.recovery_audit, {"operator": operator.strip(), "reason": reason.strip(),
            "at": now.isoformat(), "previous_status": entry.status, "fingerprint": expected_fingerprint,
            "workers_confirmed_stopped": True}]
        entry.status, entry.token, entry.finished_at, entry.message = "failed", "", now, message
        entry.save(update_fields=["recovery_audit", "status", "token", "finished_at", "message"])
        return entry
