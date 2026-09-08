from __future__ import annotations

from django.db.models import Count, Max

from bitrix24.models import (
    BitrixLead,
    BitrixLeadAnalytics,
    BitrixLeadProcessing,
    BitrixStageHistory,
    BitrixStageInterval,
    BitrixUser,
)


def _iso(value):
    return value.isoformat() if value is not None else None


def get_bitrix24_data_quality() -> dict:
    active_leads = BitrixLead.objects.filter(is_deleted=False)
    lead_ids = active_leads.values("lead_id")
    user_ids = BitrixUser.objects.filter(is_deleted=False).values("user_id")
    unmapped = list(
        BitrixLeadAnalytics.objects.filter(is_unmapped=True)
        .values("status_id", "status_name")
        .annotate(count=Count("id"))
        .order_by("status_id")
    )
    freshness = active_leads.aggregate(
        max_source_updated_at=Max("source_updated_at"),
        max_loaded_at=Max("date_update"),
    )
    history_freshness = BitrixStageHistory.objects.filter(entity_type_id=1).aggregate(
        max_created_at=Max("created_at"),
        max_loaded_at=Max("date_update"),
    )

    checks = {
        "active_leads": active_leads.count(),
        "analytics_rows": BitrixLeadAnalytics.objects.count(),
        "unmapped_status_rows": BitrixLeadAnalytics.objects.filter(
            is_unmapped=True
        ).count(),
        "leads_without_manager": active_leads.filter(
            assigned_by_id__isnull=True
        ).count(),
        "leads_with_unknown_manager": active_leads.filter(
            assigned_by_id__isnull=False
        ).exclude(assigned_by_id__in=user_ids).count(),
        "leads_without_source": active_leads.filter(source_id="").count(),
        "stage_history_without_lead": BitrixStageHistory.objects.filter(
            entity_type_id=1
        ).exclude(entity_id__in=lead_ids).count(),
        "negative_stage_durations": BitrixStageInterval.objects.filter(
            duration_seconds__lt=0
        ).count(),
        "negative_processing_durations": BitrixLeadProcessing.objects.filter(
            processing_duration_seconds__lt=0
        ).count(),
    }
    critical_keys = (
        "unmapped_status_rows",
        "leads_with_unknown_manager",
        "stage_history_without_lead",
        "negative_stage_durations",
        "negative_processing_durations",
    )
    return {
        "status": "error" if any(checks[key] for key in critical_keys) else "ok",
        "checks": checks,
        "unmapped_statuses": unmapped,
        "freshness": {
            "lead_source_updated_at": _iso(freshness["max_source_updated_at"]),
            "lead_loaded_at": _iso(freshness["max_loaded_at"]),
            "stage_history_created_at": _iso(history_freshness["max_created_at"]),
            "stage_history_loaded_at": _iso(history_freshness["max_loaded_at"]),
        },
    }
