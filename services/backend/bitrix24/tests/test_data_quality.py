from django.test import TestCase
from django.utils import timezone

from bitrix24.models import BitrixLead, BitrixLeadAnalytics, BitrixStageHistory
from bitrix24.services.data_quality import get_bitrix24_data_quality


class BitrixDataQualityTests(TestCase):
    def test_unknown_status_and_orphan_history_are_reported(self):
        now = timezone.now()
        BitrixLead.objects.create(
            lead_id=1,
            status_id="UNKNOWN",
            source_id="",
            source_created_at=now,
            source_updated_at=now,
        )
        BitrixLeadAnalytics.objects.create(
            lead_id=1,
            source_created_at=now,
            status_id="UNKNOWN",
            dashboard_status="unmapped",
            is_unmapped=True,
            calculated_at=now,
        )
        BitrixStageHistory.objects.create(
            history_id=10,
            entity_type_id=1,
            entity_id=999,
            stage_id="NEW",
            created_at=now,
        )

        result = get_bitrix24_data_quality()

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["checks"]["unmapped_status_rows"], 1)
        self.assertEqual(result["checks"]["stage_history_without_lead"], 1)
        self.assertEqual(result["checks"]["leads_without_source"], 1)
