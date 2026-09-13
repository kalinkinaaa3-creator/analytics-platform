from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from bitrix24.models import BitrixStageHistory, BitrixStageInterval, BitrixDeal


SECONDS_PER_DAY = Decimal(86400)
DAY_QUANTUM = Decimal("0.00000001")


def duration_days(seconds: int) -> Decimal:
    return (Decimal(seconds) / SECONDS_PER_DAY).quantize(DAY_QUANTUM)


def _replace_entity_intervals(
    entity_type_id: int,
    entity_id: int,
    history_rows: list[BitrixStageHistory],
    calculated_at,
) -> int:
    intervals = []
    for position, row in enumerate(history_rows):
        next_row = history_rows[position + 1] if position + 1 < len(history_rows) else None
        left_at = next_row.created_at if next_row is not None else None
        duration_end = left_at or calculated_at
        seconds = max(0, int((duration_end - row.created_at).total_seconds()))
        intervals.append(
            BitrixStageInterval(
                entity_type_id=entity_type_id,
                entity_id=entity_id,
                history_id=row.history_id,
                sequence_number=position + 1,
                stage_id=row.stage_id,
                entered_at=row.created_at,
                left_at=left_at,
                duration_seconds=seconds,
                duration_days=duration_days(seconds),
                is_current=next_row is None,
                calculated_at=calculated_at,
            )
        )

    with transaction.atomic():
        BitrixStageInterval.objects.filter(
            entity_type_id=entity_type_id,
            entity_id=entity_id,
        ).delete()
        BitrixStageInterval.objects.bulk_create(intervals)
    return len(intervals)


def rebuild_stage_intervals(
    *,
    entity_type_id: int = 1,
    entity_ids=None,
    calculated_at=None,
    iterator_chunk_size: int = 1000,
) -> tuple[int, set[int]]:
    calculated_at = calculated_at or timezone.now()
    queryset = BitrixStageHistory.objects.filter(entity_type_id=entity_type_id)
    if entity_type_id == 2:
        queryset = queryset.exclude(entity_id__in=BitrixDeal.objects.filter(is_deleted=True).values("deal_id"))
    if entity_ids is not None:
        queryset = queryset.filter(entity_id__in=entity_ids)
    queryset = queryset.only("history_id", "entity_id", "stage_id", "created_at").order_by("entity_id", "created_at", "history_id")

    current_entity_id = None
    current_rows = []
    interval_count = 0
    affected = set()
    for row in queryset.iterator(chunk_size=iterator_chunk_size):
        if current_entity_id is not None and row.entity_id != current_entity_id:
            interval_count += _replace_entity_intervals(
                entity_type_id,
                current_entity_id,
                current_rows,
                calculated_at,
            )
            affected.add(current_entity_id)
            current_rows = []
        current_entity_id = row.entity_id
        current_rows.append(row)

    if current_entity_id is not None:
        interval_count += _replace_entity_intervals(
            entity_type_id,
            current_entity_id,
            current_rows,
            calculated_at,
        )
        affected.add(current_entity_id)
    return interval_count, affected
