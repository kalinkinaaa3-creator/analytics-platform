from __future__ import annotations

from django.utils import timezone

from bitrix24.models import (
    BitrixCrmDictionary,
    BitrixDashboardStatusMap,
    BitrixDepartment,
    BitrixLead,
    BitrixLeadAnalytics,
    BitrixLeadProcessing,
    BitrixManagerTracking,
    BitrixUser,
)


UNMAPPED = BitrixDashboardStatusMap.DashboardStatus.UNMAPPED


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
    status_maps = {
        item.status_id: item
        for item in BitrixDashboardStatusMap.objects.filter(
            entity_id="STATUS",
            is_active=True,
        )
    }
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
            "department_id",
            "name",
        )
    )
    tracking_rows = list(
        BitrixManagerTracking.objects.select_related("department").all()
    )
    tracking_by_user = {item.user_id: item for item in tracking_rows}
    if tracking_rows:
        leads = leads.filter(
            assigned_by_id__in=[
                item.user_id for item in tracking_rows if item.is_tracked
            ]
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
            status_map = status_maps.get(lead.status_id)
            user = users.get(lead.assigned_by_id)
            tracking = tracking_by_user.get(lead.assigned_by_id)
            primary_department_id = (
                tracking.department.department_id
                if tracking is not None
                else (user.primary_department_id if user else None)
            )
            lead_processing = processing.get(lead.lead_id)
            is_apm = status_map.is_apm if status_map else False
            is_low_quality = status_map.is_low_quality if status_map else False
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
                    dashboard_status=(status_map.dashboard_status if status_map else UNMAPPED),
                    manager_id=lead.assigned_by_id,
                    manager_name=user.full_name if user else "",
                    primary_department_id=primary_department_id,
                    department_name=(
                        tracking.department.name
                        if tracking is not None
                        else departments.get(primary_department_id, "")
                    ),
                    is_apm=is_apm,
                    is_low_quality=is_low_quality and not is_apm,
                    is_unmapped=status_map is None,
                    is_processed=status_map.is_processed if status_map else False,
                    is_final=status_map.is_final if status_map else False,
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
