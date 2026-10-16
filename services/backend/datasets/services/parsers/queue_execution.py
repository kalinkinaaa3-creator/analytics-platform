"""Admission adapters. Enable only after migration and PostgreSQL rollout checks."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
import os
from threading import Event, Thread
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connections
from organizations.models import Organization
from datasets.models import ParserMasterPipelineRun, TaraRun
from datasets.parser_queue_models import ParserQueueEntry
from . import global_queue as queue

logger = logging.getLogger(__name__)
_current = ContextVar("parser_queue_owner", default=None)


def enabled():
    return getattr(settings, "PARSER_SHARED_QUEUE_ENABLED", False)


def _entry(kind, run_id, *, organization_code="iplast"):
    return queue.enqueue(organization=Organization.objects.get(code=organization_code), kind=kind, run_id=run_id)


def register_master(run_id, *, workspace=None):
    # Register before process launch so FIFO reflects requests, not OS scheduling.
    return _entry("master", run_id, organization_code=workspace.code if workspace else "iplast")


def register_tara(run):
    organization_code = "select-market" if run._meta.app_label == "select_market" else "iplast"
    if enabled() and not run.master_id:
        return _entry("tara", run.pk, organization_code=organization_code)


def master_queue_status(run_id):
    if not enabled():
        return None
    entry = ParserQueueEntry.objects.filter(organization__code="iplast", kind="master", run_id=run_id).first()
    if entry is None:
        return None
    message = entry.message
    if entry.status == "queued":
        message = "Ожидание общего слота парсеров. Одновременно выполняется один сбор."
    return {"status": entry.status, "message": message}


def _claim(entry):
    executor = f"backend:{os.getpid()}"
    if entry.status == "queued":
        return queue.claim_next(executor=executor, entry_id=entry.pk)
    if entry.status == "waiting_remote":
        return queue.resume(entry.pk, entry.token, executor=executor)
    return None


@contextmanager
def _execution(entry):
    stopped = Event()
    context = _current.set((entry.pk, entry.token))

    def pulse():
        try:
            while not stopped.wait(20):
                close_old_connections()
                try:
                    queue.heartbeat(entry.pk, entry.token)
                except Exception:
                    logger.exception("Parser queue heartbeat failed: %s", entry.pk)
                    return
        finally:
            connections.close_all()

    thread = Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=5)
        _current.reset(context)


def _validate_context(organization_code="iplast"):
    owner = _current.get()
    if owner is None:
        return False
    if not ParserQueueEntry.objects.filter(pk=owner[0], token=owner[1], organization__code=organization_code, status__in=("running", "waiting_remote")).exists():
        raise queue.QueueOwnershipError("Parser execution no longer owns shared capacity")
    return True


def standalone(kind):
    """Manual source commands fail clearly when busy; they never bypass capacity."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            workspace = kwargs.get("workspace")
            organization_code = workspace.code if workspace is not None else "iplast"
            if organization_code != "iplast" and not enabled():
                raise queue.QueueOwnershipError("Сначала включите и проверьте общую очередь парсеров.")
            if not enabled() or _validate_context(organization_code):
                return function(*args, **kwargs)
            entry = _entry(kind, uuid4().int % (2**63 - 1) + 1, organization_code=organization_code)
            active = _claim(entry)
            if active is None:
                queue.cancel_queued(entry.pk, organization=entry.organization)
                raise queue.QueueOwnershipError("Парсеры заняты. Дождитесь завершения текущего сбора и повторите команду.")
            success = False
            try:
                with _execution(active):
                    result = function(*args, **kwargs)
                    success = True
                    return result
            finally:
                queue.finish(active.pk, active.token, success=success)
        return wrapped
    return decorate


def master(function):
    @wraps(function)
    def wrapped(*, run_id, workspace=None):
        ParserMasterPipelineRun = workspace.model("ParserMasterPipelineRun") if workspace else globals()["ParserMasterPipelineRun"]
        TaraRun = workspace.model("TaraRun") if workspace else globals()["TaraRun"]
        options = {"workspace": workspace} if workspace else {}
        if workspace and workspace.code == "select-market" and not enabled():
            raise queue.QueueOwnershipError("Shared parser queue is disabled")
        if not enabled():
            return function(run_id=run_id, **options)
        run = ParserMasterPipelineRun.objects.get(pk=run_id)
        if run.status in ("success", "failed", "cancelled"):
            return {"run_id": run_id, "status": run.status}
        entry = register_master(run_id, workspace=workspace)
        if entry.status == "waiting_remote" and TaraRun.objects.filter(master_id=run_id, status__in=TaraRun.ACTIVE).exists():
            return {"run_id": run_id, "status": "waiting_tara"}
        active = _claim(entry)
        if active is None:
            return {"run_id": run_id, "status": "queued", "waiting_for_capacity": True}
        try:
            with _execution(active):
                return function(run_id=run_id, **options)
        finally:
            run.refresh_from_db()
            child_active = TaraRun.objects.filter(master_id=run_id, status__in=TaraRun.ACTIVE).exists()
            if child_active or run.status in ("waiting_tara", "waiting_session"):
                queue.wait_for_remote(active.pk, active.token, message="Ожидание завершения ТАРА")
            elif run.status in ("success", "failed", "cancelled"):
                queue.finish(active.pk, active.token, success=run.status == "success")
            else:
                # Unexpected exit: retain ownership for investigation, never expire it.
                ParserQueueEntry.objects.filter(pk=active.pk, token=active.token).update(
                    status="recovery_required", message="Мастер завершился без итогового статуса.")
    return wrapped


def tara_can_dispatch(run):
    organization_code = "select-market" if run._meta.app_label == "select_market" else "iplast"
    if organization_code == "select-market" and not enabled():
        return False
    if not enabled():
        return True
    entry = _entry("master" if run.master_id else "tara", run.master_id or run.pk, organization_code=organization_code)
    if run.master_id:
        return entry.status in ("running", "waiting_remote")
    if entry.status == "waiting_remote":
        return True
    if entry.status != "queued":
        return False
    if ParserQueueEntry.objects.filter(status__in=ParserQueueEntry.OCCUPIED).exists():
        return False
    return ParserQueueEntry.objects.filter(status="queued").order_by("id").values_list("id", flat=True).first() == entry.pk


def tara(function):
    @wraps(function)
    def wrapped(run_id, lease, *, workspace=None):
        organization_code = workspace.code if workspace else "iplast"
        TaraRun = workspace.model("TaraRun") if workspace else globals()["TaraRun"]
        ParserMasterPipelineRun = workspace.model("ParserMasterPipelineRun") if workspace else globals()["ParserMasterPipelineRun"]
        call_options = {"workspace": workspace} if workspace else {}
        if organization_code == "select-market" and not enabled():
            raise queue.QueueOwnershipError("Shared parser queue is disabled")
        if not enabled():
            return function(run_id, lease, **call_options)
        run = TaraRun.objects.get(pk=run_id)
        if run.lease != lease or run.status != "dispatching":
            return
        entry = _entry("master" if run.master_id else "tara", run.master_id or run.pk, organization_code=organization_code)
        active = entry if run.master_id and entry.status in ("running", "waiting_remote") else None
        if not run.master_id:
            active = _claim(entry)
        if active is None:
            TaraRun.objects.filter(pk=run_id, lease=lease, status="dispatching").update(status="queued", lease="")
            return
        try:
            with _execution(active):
                return function(run_id, lease, **call_options)
        finally:
            if run.master_id:
                parent = ParserMasterPipelineRun.objects.get(pk=run.master_id)
                entry.refresh_from_db()
                if (parent.status in ("failed", "cancelled", "success")
                        and entry.status == "waiting_remote"
                        and not TaraRun.objects.filter(master_id=parent.pk, status__in=TaraRun.ACTIVE).exists()):
                    # This executor has returned and joined its child threads.
                    # A user cancellation alone is not sufficient for this release.
                    owner = queue.resume(entry.pk, entry.token, executor=f"tara-finished:{os.getpid()}")
                    queue.finish(owner.pk, owner.token, success=parent.status == "success")
            else:
                run.refresh_from_db()
                if run.status in ("success", "failed", "cancelled"):
                    queue.finish(active.pk, active.token, success=run.status == "success")
                else:
                    queue.wait_for_remote(active.pk, active.token, message="Ожидание ТАРА или повторной попытки")
    return wrapped


def dispatch_waiting_masters():
    """Periodic maintenance retries the head only; admission occurs in its process."""
    if not enabled():
        return
    from .master_pipeline_launcher import launch_parser_master_pipeline
    queue.flag_stalled()
    if ParserQueueEntry.objects.filter(status__in=ParserQueueEntry.OCCUPIED).exists():
        return
    head = ParserQueueEntry.objects.filter(status="queued").select_related("organization").order_by("id").first()
    if head and head.kind == "master":
        from datasets.services.iprice_workspace import workspace_for
        workspace = workspace_for(head.organization) if head.organization.code != "iplast" else None
        model = workspace.model("ParserMasterPipelineRun") if workspace else ParserMasterPipelineRun
        run = model.objects.get(pk=head.run_id)
        if run.status == "queued":
            launch_parser_master_pipeline(run.pk, **({"workspace": workspace} if workspace else {}))
        elif run.status in ("success", "failed", "cancelled"):
            queue.cancel_queued(head.pk, organization=head.organization)
