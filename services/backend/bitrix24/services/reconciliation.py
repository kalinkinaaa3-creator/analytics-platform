from django.db import transaction
from django.db.models import Subquery

from bitrix24.models import (
    BitrixLead,
    BitrixLeadAnalytics,
    BitrixLeadProcessing,
    BitrixStageInterval,
)


LEAD_ENTITY_TYPE_ID = 1


@transaction.atomic
def purge_deleted_lead_derivatives() -> dict[str, int]:
    """Remove calculated rows for deleted leads while retaining raw CRM history."""
    deleted_lead_ids = BitrixLead.objects.filter(is_deleted=True).values("lead_id")
    analytics, _ = BitrixLeadAnalytics.objects.filter(
        lead_id__in=Subquery(deleted_lead_ids)
    ).delete()
    processing, _ = BitrixLeadProcessing.objects.filter(
        lead_id__in=Subquery(deleted_lead_ids)
    ).delete()
    intervals, _ = BitrixStageInterval.objects.filter(
        entity_type_id=LEAD_ENTITY_TYPE_ID,
        entity_id__in=Subquery(deleted_lead_ids),
    ).delete()
    return {
        "analytics": analytics,
        "processing": processing,
        "intervals": intervals,
    }
