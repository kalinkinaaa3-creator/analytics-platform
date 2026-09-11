from __future__ import annotations

from django.utils import timezone

import json

from bitrix24.models import (
    BitrixCrmDictionary,
    BitrixCrmField,
    BitrixDepartment,
    BitrixLead,
    BitrixLeadAnalytics,
    BitrixLeadProcessing,
    BitrixUser,
)
from bitrix24.services.dashboard_query import UNTRACKED_DEPARTMENT_NAME


APM_STATUS_ID = "5"


def _stage_group(lead):
    if lead.status_id == APM_STATUS_ID:
        return "apm"
    semantic = (lead.status_semantic_id or "").strip().upper()
    return {
        "S": "target",
        "F": "low_quality",
        "P": "in_progress",
    }.get(semantic, "unknown")


def _enumeration_names(field_code="UF_CRM_1680165215489"):
    row = BitrixCrmField.objects.filter(
        entity_type_id=1,
        field_code=field_code,
        is_deleted=False,
    ).values_list("raw_payload", flat=True).first() or {}
    if isinstance(row, str):
        try:
            row = json.loads(row)
        except (TypeError, ValueError):
            row = {}
    return {
        str(item.get("ID")): str(item.get("VALUE") or "")
        for item in row.get("items", [])
        if item.get("ID") is not None
    }


def rebuild_lead_analytics(*, lead_ids=None, calculated_at=None) -> int:
    calculated_at = calculated_at or timezone.now()
    leads = BitrixLead.objects.filter(is_deleted=False)
    if lead_ids is not None:
        leads = leads.filter(lead_id__in=lead_ids)

    status_names = dict(
        BitrixCrmDictionary.objects.filter(entity_id="STATUS", is_deleted=False)
        .values_list("status_id", "name")
    )
    source_names = dict(
        BitrixCrmDictionary.objects.filter(entity_id="SOURCE", is_deleted=False)
        .values_list("status_id", "name")
    )
    activity_names = _enumeration_names()
    project_names = _enumeration_names("UF_CRM_1707131669360")
    users = {
        item.user_id: item
        for item in BitrixUser.objects.filter(is_deleted=False).only(
            "user_id",
            "full_name",
            "primary_department_id",
        )
    }
    departments = dict(
        BitrixDepartment.objects.filter(is_deleted=False).values_list(
            "department_id", "name"
        )
    )
    update_fields = tuple(
        field.name
        for field in BitrixLeadAnalytics._meta.fields
        if field.name not in {"id", "lead_id"}
    )

    def flush(batch):
        if not batch:
            return 0
        processing = {
            item.lead_id: item
            for item in BitrixLeadProcessing.objects.filter(
                lead_id__in=[lead.lead_id for lead in batch]
            )
        }
        objects = []
        for lead in batch:
            user = users.get(lead.assigned_by_id)
            primary_department_id = (
                user.primary_department_id if user else None
            )
            lead_processing = processing.get(lead.lead_id)
            stage_group = _stage_group(lead)
            objects.append(
                BitrixLeadAnalytics(
                    lead_id=lead.lead_id,
                    title=lead.title,
                    source_created_at=lead.source_created_at,
                    source_updated_at=lead.source_updated_at,
                    opportunity=lead.opportunity,
                    source_id=lead.source_id,
                    source_name=source_names.get(lead.source_id, ""),
                    status_id=lead.status_id,
                    status_name=status_names.get(lead.status_id, ""),
                    status_semantic_id=lead.status_semantic_id,
                    dashboard_status=stage_group,
                    manager_id=lead.assigned_by_id,
                    manager_name=user.full_name if user else "",
                    primary_department_id=primary_department_id,
                    department_name=(
                        departments.get(primary_department_id)
                        or UNTRACKED_DEPARTMENT_NAME
                    ),
                    company_name=lead.company_title or lead.name or lead.title,
                    is_return_customer=lead.is_return_customer,
                    project_id=lead.project_id,
                    project_name=project_names.get(lead.project_id, lead.project_id),
                    activity_name=activity_names.get(lead.activity_event_id, ""),
                    last_activity_time=lead.last_activity_time,
                    is_apm=stage_group == "apm",
                    is_low_quality=stage_group == "low_quality",
                    is_unmapped=stage_group == "unknown",
                    is_processed=stage_group in {"target", "low_quality", "apm"},
                    is_final=stage_group in {"target", "low_quality", "apm"},
                    first_processing_at=(
                        lead_processing.first_processing_at if lead_processing else None
                    ),
                    processing_duration_seconds=(
                        lead_processing.processing_duration_seconds
                        if lead_processing
                        else None
                    ),
                    processing_duration_days=(
                        lead_processing.processing_duration_days
                        if lead_processing
                        else None
                    ),
                    processing_state=(
                        lead_processing.processing_state if lead_processing else ""
                    ),
                    calculated_at=calculated_at,
                )
            )
        BitrixLeadAnalytics.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=("lead_id",),
            update_fields=update_fields,
        )
        return len(objects)

    count = 0
    batch = []
    for lead in leads.iterator(chunk_size=500):
        batch.append(lead)
        if len(batch) >= 500:
            count += flush(batch)
            batch = []
    count += flush(batch)

    if lead_ids is None:
        retained_ids = leads.values("lead_id")
        BitrixLeadAnalytics.objects.exclude(lead_id__in=retained_ids).delete()
    else:
        retained_ids = leads.values("lead_id")
        BitrixLeadAnalytics.objects.filter(lead_id__in=lead_ids).exclude(
            lead_id__in=retained_ids
        ).delete()
    return count
