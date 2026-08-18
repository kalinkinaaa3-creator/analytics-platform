from __future__ import annotations

from django.utils import timezone

from bitrix24.models import BitrixLead, BitrixLeadProcessing, BitrixStageInterval

from .stage_intervals import duration_days


LEAD_ENTITY_TYPE_ID = 1
INITIAL_STATUS_ID = "NEW"


def _processing_result(lead, intervals, calculated_at):
    if not intervals:
        return BitrixLeadProcessing(
            lead_id=lead.lead_id,
            processing_started_at=lead.source_created_at,
            processing_state=BitrixLeadProcessing.ProcessingState.NO_HISTORY,
            current_status_id=lead.status_id,
            calculated_at=calculated_at,
        )

    started_at = lead.source_created_at or intervals[0].entered_at
    first_stage_change_at = next(
        (
            interval.entered_at
            for interval in intervals[1:]
            if interval.stage_id != intervals[0].stage_id
        ),
        None,
    )
    first_processing_at = None
    state = BitrixLeadProcessing.ProcessingState.INVALID_HISTORY
    if intervals[0].stage_id == INITIAL_STATUS_ID:
        first_processing_at = next(
            (
                interval.entered_at
                for interval in intervals[1:]
                if interval.stage_id != INITIAL_STATUS_ID
            ),
            None,
        )
        state = (
            BitrixLeadProcessing.ProcessingState.COMPLETED
            if first_processing_at is not None
            else BitrixLeadProcessing.ProcessingState.IN_PROGRESS
        )

    duration_end = first_processing_at
    if state == BitrixLeadProcessing.ProcessingState.IN_PROGRESS:
        duration_end = calculated_at
    processing_seconds = None
    if duration_end is not None and started_at is not None:
        processing_seconds = max(0, int((duration_end - started_at).total_seconds()))

    current = intervals[-1]
    current_seconds = max(0, int((calculated_at - current.entered_at).total_seconds()))
    return BitrixLeadProcessing(
        lead_id=lead.lead_id,
        processing_started_at=started_at,
        first_stage_change_at=first_stage_change_at,
        first_processing_at=first_processing_at,
        processing_duration_seconds=processing_seconds,
        processing_duration_days=(
            duration_days(processing_seconds) if processing_seconds is not None else None
        ),
        processing_state=state,
        current_status_id=current.stage_id,
        current_status_since=current.entered_at,
        current_status_duration_seconds=current_seconds,
        current_status_duration_days=duration_days(current_seconds),
        calculated_at=calculated_at,
    )


def rebuild_lead_processing(*, lead_ids=None, calculated_at=None) -> int:
    calculated_at = calculated_at or timezone.now()
    leads = BitrixLead.objects.filter(is_deleted=False)
    if lead_ids is not None:
        leads = leads.filter(lead_id__in=lead_ids)

    update_fields = tuple(
        field.name
        for field in BitrixLeadProcessing._meta.fields
        if field.name not in {"id", "lead_id"}
    )
    count = 0
    lead_batch = []

    def flush(batch):
        if not batch:
            return 0
        batch_ids = [lead.lead_id for lead in batch]
        intervals_by_lead = {lead_id: [] for lead_id in batch_ids}
        intervals = BitrixStageInterval.objects.filter(
            entity_type_id=LEAD_ENTITY_TYPE_ID,
            entity_id__in=batch_ids,
        ).order_by("entity_id", "sequence_number")
        for interval in intervals.iterator(chunk_size=1000):
            intervals_by_lead[interval.entity_id].append(interval)
        objects = [
            _processing_result(
                lead,
                intervals_by_lead[lead.lead_id],
                calculated_at,
            )
            for lead in batch
        ]
        BitrixLeadProcessing.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=("lead_id",),
            update_fields=update_fields,
        )
        return len(objects)

    for lead in leads.iterator(chunk_size=500):
        lead_batch.append(lead)
        if len(lead_batch) >= 500:
            count += flush(lead_batch)
            lead_batch = []
    count += flush(lead_batch)
    return count
