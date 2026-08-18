from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from bitrix24.models import (
    BitrixCrmDictionary,
    BitrixDashboardStatusMap,
    BitrixDepartment,
    BitrixLead,
    BitrixLeadAnalytics,
    BitrixManagerTracking,
    BitrixUser,
)
from bitrix24.services.calculators import rebuild_lead_analytics


class LeadAnalyticsTests(TestCase):
    def setUp(self):
        BitrixDepartment.objects.create(department_id=10, name="Продажи")
        BitrixUser.objects.create(
            user_id=20,
            full_name="Иванов Иван",
            department_ids=[10],
            primary_department_id=10,
        )
        BitrixCrmDictionary.objects.bulk_create(
            [
                BitrixCrmDictionary(
                    entity_id="STATUS",
                    status_id="5",
                    name="Передано в Айпласт Маркет",
                ),
                BitrixCrmDictionary(
                    entity_id="SOURCE",
                    status_id="WEB",
                    name="Сайт",
                ),
            ]
        )

    def test_apm_lead_is_not_low_quality(self):
        BitrixDashboardStatusMap.objects.update_or_create(
            entity_id="STATUS",
            status_id="5",
            defaults={
                "dashboard_status": BitrixDashboardStatusMap.DashboardStatus.CONVERTED,
                "display_name": "Передано в Айпласт Маркет",
                "is_apm": True,
                "is_processed": True,
            },
        )
        BitrixLead.objects.create(
            lead_id=100,
            status_id="5",
            source_id="WEB",
            assigned_by_id=20,
            source_created_at=timezone.now(),
        )

        rebuild_lead_analytics()

        result = BitrixLeadAnalytics.objects.get(lead_id=100)
        self.assertTrue(result.is_apm)
        self.assertFalse(result.is_low_quality)
        self.assertFalse(result.is_unmapped)
        self.assertEqual(result.primary_department_id, 10)
        self.assertEqual(result.department_name, "Продажи")

    def test_unknown_status_is_unmapped_not_low_quality(self):
        BitrixLead.objects.create(
            lead_id=101,
            status_id="NEW_UNKNOWN_STATUS",
            source_created_at=timezone.now(),
        )

        rebuild_lead_analytics()

        result = BitrixLeadAnalytics.objects.get(lead_id=101)
        self.assertEqual(result.dashboard_status, "unmapped")
        self.assertTrue(result.is_unmapped)
        self.assertFalse(result.is_low_quality)

    def test_status_cannot_be_apm_and_low_quality(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BitrixDashboardStatusMap.objects.create(
                entity_id="STATUS",
                status_id="INVALID",
                is_apm=True,
                is_low_quality=True,
            )

    def test_tracking_configuration_filters_leads_and_overrides_department(self):
        second_department = BitrixDepartment.objects.create(
            department_id=11, name="Региональные продажи"
        )
        BitrixUser.objects.create(user_id=21, full_name="Петров Пётр")
        BitrixManagerTracking.objects.create(
            user_id=20,
            manager_name="Иванов Иван",
            department=second_department,
            is_tracked=True,
        )
        BitrixLead.objects.bulk_create(
            [
                BitrixLead(lead_id=201, assigned_by_id=20),
                BitrixLead(lead_id=202, assigned_by_id=21),
            ]
        )

        rebuild_lead_analytics()

        tracked = BitrixLeadAnalytics.objects.get(lead_id=201)
        self.assertEqual(tracked.primary_department_id, 11)
        self.assertEqual(tracked.department_name, "Региональные продажи")
        self.assertFalse(BitrixLeadAnalytics.objects.filter(lead_id=202).exists())
