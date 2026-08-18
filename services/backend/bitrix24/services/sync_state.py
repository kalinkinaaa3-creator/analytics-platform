from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from bitrix24.models import BitrixSyncRun, BitrixSyncState


_UNSET = object()


class BitrixSyncAlreadyRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class BitrixSyncStats:
    rows_received: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_deactivated: int = 0


def get_incremental_from(entity: str, overlap: timedelta) -> datetime | None:
    state = BitrixSyncState.objects.filter(entity=entity).only(
        "last_source_updated_at"
    ).first()
    if state is None or state.last_source_updated_at is None:
        return None
    return state.last_source_updated_at - overlap


@transaction.atomic
def start_sync(
    entity: str,
    mode: str,
    *,
    source_updated_from=None,
) -> BitrixSyncRun:
    state, _ = BitrixSyncState.objects.select_for_update().get_or_create(entity=entity)
    if state.status == BitrixSyncState.Status.RUNNING:
        raise BitrixSyncAlreadyRunning(f"Bitrix24 sync is already running for {entity}.")

    run = BitrixSyncRun.objects.create(
        entity=entity,
        mode=mode,
        source_updated_from=source_updated_from,
    )
    state.status = BitrixSyncState.Status.RUNNING
    state.started_at = run.started_at
    state.finished_at = None
    state.error_text = ""
    state.last_run = run
    state.save(
        update_fields=(
            "status",
            "started_at",
            "finished_at",
            "error_text",
            "last_run",
            "date_update",
        )
    )
    return run


@transaction.atomic
def finish_sync(
    run: BitrixSyncRun,
    *,
    stats: BitrixSyncStats,
    last_source_updated_at=_UNSET,
    last_source_id: int | None | object = _UNSET,
) -> None:
    finished_at = timezone.now()
    state = BitrixSyncState.objects.select_for_update().get(entity=run.entity)

    run.status = BitrixSyncRun.Status.SUCCESS
    run.finished_at = finished_at
    run.source_updated_to = (
        None if last_source_updated_at is _UNSET else last_source_updated_at
    )
    run.rows_received = stats.rows_received
    run.rows_created = stats.rows_created
    run.rows_updated = stats.rows_updated
    run.rows_deactivated = stats.rows_deactivated
    run.error_text = ""
    run.save()

    state.status = BitrixSyncState.Status.SUCCESS
    state.last_success_at = finished_at
    if last_source_updated_at is not _UNSET:
        state.last_source_updated_at = last_source_updated_at
    if last_source_id is not _UNSET:
        state.last_source_id = last_source_id
    state.finished_at = finished_at
    state.rows_received = stats.rows_received
    state.rows_created = stats.rows_created
    state.rows_updated = stats.rows_updated
    state.rows_deactivated = stats.rows_deactivated
    state.error_text = ""
    state.last_run = run
    state.save()


@transaction.atomic
def fail_sync(run: BitrixSyncRun, error: BaseException) -> None:
    finished_at = timezone.now()
    error_text = f"{type(error).__name__}: {error}"[:4000]
    state = BitrixSyncState.objects.select_for_update().get(entity=run.entity)

    run.status = BitrixSyncRun.Status.FAILED
    run.finished_at = finished_at
    run.error_text = error_text
    run.save(update_fields=("status", "finished_at", "error_text"))

    state.status = BitrixSyncState.Status.FAILED
    state.finished_at = finished_at
    state.error_text = error_text
    state.last_run = run
    state.save(
        update_fields=(
            "status",
            "finished_at",
            "error_text",
            "last_run",
            "date_update",
        )
    )
