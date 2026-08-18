import os
from datetime import date

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from bitrix24.models import BitrixLeadAnalytics
from bitrix24.services.dashboard_query import (
    LeadDashboardFilters,
    LeadDashboardQuery,
)
from bitrix24.services.export import export_leads_xlsx


class FakeClickHouseClient:
    def __init__(self):
        self.queries = []

    def execute(self, sql, params, with_column_types=False):
        self.queries.append((sql, params))
        if "dashboard_status" in sql and "GROUP BY period, dashboard_status" in sql:
            return [], [("period", "Date"), ("dashboard_status", "String"), ("value", "UInt64")]
        return [], [("period", "Date"), ("value", "UInt64")]


class DashboardQueryTests(TestCase):
    def test_apm_is_excluded_only_from_low_quality_dynamics(self):
        client = FakeClickHouseClient()
        query = LeadDashboardQuery(client=client)
        filters = LeadDashboardFilters(
            date_start=date(2026, 1, 1),
            date_end=date(2026, 8, 18),
        )

        query.lead_dynamics(filters)
        lead_sql = client.queries[-1][0]
        query.status_dynamics(filters)
        status_sql = client.queries[-1][0]
        query.low_quality_dynamics(filters)
        low_quality_sql = client.queries[-1][0]

        self.assertNotIn("is_apm = 0", lead_sql)
        self.assertNotIn("is_apm = 0", status_sql)
        self.assertIn("is_apm = 0", low_quality_sql)

    def test_export_contains_filtered_lead(self):
        now = timezone.now()
        BitrixLeadAnalytics.objects.create(
            lead_id=100,
            source_created_at=now,
            source_id="WEB",
            source_name="Сайт",
            status_id="NEW",
            status_name="Новый",
            dashboard_status="unprocessed",
            calculated_at=now,
        )
        path, count = export_leads_xlsx(
            LeadDashboardFilters(
                date_start=now.date(),
                date_end=now.date(),
                source_ids=("WEB",),
            )
        )
        try:
            workbook = load_workbook(path, read_only=True)
            rows = list(workbook["Лидогенерация"].iter_rows(values_only=True))
            workbook.close()
            self.assertEqual(count, 1)
            self.assertEqual(rows[1][0], 100)
        finally:
            os.unlink(path)
