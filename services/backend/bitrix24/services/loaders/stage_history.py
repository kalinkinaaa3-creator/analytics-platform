from __future__ import annotations

from datetime import datetime, timedelta

from bitrix24.models import BitrixStageHistory, BitrixSyncRun
from bitrix24.services.client import Bitrix24Client, Bitrix24ResponseError
from bitrix24.services.sync_state import (
    BitrixSyncStats,
    fail_sync,
    finish_sync,
    get_incremental_from,
    start_sync,
)

from .common import as_datetime, as_int, source_value, text


def load_stage_history(
    client: Bitrix24Client,
    *,
    entity_type_id: int = 1,
    mode: str = BitrixSyncRun.Mode.INCREMENTAL,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    overlap: timedelta = timedelta(minutes=10),
) -> tuple[BitrixSyncRun, set[int]]:
    if mode not in BitrixSyncRun.Mode.values:
        raise ValueError(f"Unsupported Bitrix24 sync mode: {mode}.")

    entity = f"stage_history_{entity_type_id}"
    if date_from is None and mode == BitrixSyncRun.Mode.INCREMENTAL:
        date_from = get_incremental_from(entity, overlap)

    filters = {}
    if date_from is not None:
        filters[">=CREATED_TIME"] = date_from.isoformat()
    if date_to is not None:
        filters["<=CREATED_TIME"] = date_to.isoformat()
    params = {
        "entityTypeId": entity_type_id,
        "order": {"CREATED_TIME": "ASC", "ID": "ASC"},
    }
    if filters:
        params["filter"] = filters

    run = start_sync(entity, mode, source_updated_from=date_from)
    received = created = updated = 0
    affected_entity_ids: set[int] = set()
    max_source_position = None
    try:
        for page in client.iter_pages("crm.stagehistory.list", params):
            objects = []
            history_ids = []
            for row in page:
                history_id = as_int(source_value(row, "ID", "id"))
                entity_id = as_int(
                    source_value(row, "OWNER_ID", "ENTITY_ID", "ownerId", "entityId")
                )
                created_at = as_datetime(
                    source_value(row, "CREATED_TIME", "createdTime")
                )
                if history_id is None or entity_id is None or created_at is None:
                    raise Bitrix24ResponseError(
                        "Stage history row has no valid ID, entity ID or creation time."
                    )
                objects.append(
                    BitrixStageHistory(
                        history_id=history_id,
                        entity_type_id=entity_type_id,
                        entity_id=entity_id,
                        category_id=as_int(
                            source_value(row, "CATEGORY_ID", "categoryId")
                        ),
                        stage_id=text(source_value(row, "STAGE_ID", "STATUS_ID", "stageId", "statusId")),
                        stage_semantic_id=text(
                            source_value(
                                row,
                                "STAGE_SEMANTIC_ID",
                                "STATUS_SEMANTIC_ID",
                                "stageSemanticId",
                                "statusSemanticId",
                            )
                        ),
                        created_at=created_at,
                        created_by_id=as_int(
                            source_value(row, "CREATED_BY_ID", "createdById")
                        ),
                        raw_payload=row,
                    )
                )
                history_ids.append(history_id)
                affected_entity_ids.add(entity_id)
                candidate = (created_at, history_id)
                if max_source_position is None or candidate > max_source_position:
                    max_source_position = candidate

            existing = set(
                BitrixStageHistory.objects.filter(
                    entity_type_id=entity_type_id,
                    history_id__in=history_ids,
                ).values_list("history_id", flat=True)
            )
            BitrixStageHistory.objects.bulk_create(
                objects,
                update_conflicts=True,
                unique_fields=("entity_type_id", "history_id"),
                update_fields=(
                    "entity_id",
                    "category_id",
                    "stage_id",
                    "stage_semantic_id",
                    "created_at",
                    "created_by_id",
                    "raw_payload",
                    "date_update",
                ),
            )
            received += len(objects)
            created += len(objects) - len(existing)
            updated += len(existing)

        finish_kwargs = {}
        if max_source_position is not None:
            finish_kwargs = {
                "last_source_updated_at": max_source_position[0],
                "last_source_id": max_source_position[1],
            }
        finish_sync(
            run,
            stats=BitrixSyncStats(received, created, updated, 0),
            **finish_kwargs,
        )
        return run, affected_entity_ids
    except BaseException as exc:
        fail_sync(run, exc)
        raise
