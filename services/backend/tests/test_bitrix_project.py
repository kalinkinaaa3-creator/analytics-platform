from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from bitrix24.api.serializers import LeadDashboardRowsRequestSerializer
from bitrix24.models import BitrixCrmField, BitrixLeadAnalytics
from bitrix24.services.calculators.lead_analytics import rebuild_lead_analytics
from bitrix24.services.clickhouse import COLUMNS, _row
from bitrix24.services.dashboard_query import LeadDashboardFilters, LeadDashboardQuery
from bitrix24.services.export import export_leads_xlsx, filtered_lead_analytics_queryset
from bitrix24.services.loaders.leads import LEAD_SELECT, _normalize_lead, load_leads


class ProjectTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        BitrixCrmField.objects.create(
            entity_type_id=1, field_code="UF_CRM_1707131669360",
            raw_payload={"items": [{"ID": "2117", "VALUE": "Project A"}]},
        )
        for lead_id, value in enumerate(["2117", None, "", "9999"], 1):
            lead = _normalize_lead({"ID": lead_id, "UF_CRM_1707131669360": value,
                                    "DATE_CREATE": self.now.isoformat()}, seen_at=self.now)
            lead.save()
        rebuild_lead_analytics()

    def filters(self, project_ids):
        return LeadDashboardFilters(date_start=date(2020, 1, 1), date_end=date(2099, 1, 1),
                                    project_ids=project_ids, exclude_untracked_department=False)

    def test_project_loading_dictionary_and_clickhouse_row(self):
        self.assertIn("UF_CRM_1707131669360", LEAD_SELECT)
        rows = {r.lead_id: r for r in BitrixLeadAnalytics.objects.all()}
        self.assertEqual(rows[1].project_name, "Project A")
        self.assertEqual(rows[2].project_id, "")
        self.assertEqual(rows[3].project_name, "")
        self.assertEqual(rows[4].project_name, "9999")
        self.assertEqual(dict(zip(COLUMNS, _row(rows[1])))["project_id"], "2117")
        self.assertEqual(len(COLUMNS), len(_row(rows[1])))

    def test_empty_project_filter_and_export(self):
        filters = self.filters(("",))
        self.assertEqual(set(filtered_lead_analytics_queryset(filters).values_list("lead_id", flat=True)), {2, 3})
        where, params = LeadDashboardQuery._where(filters)
        self.assertIn("project_id", where)
        self.assertEqual(tuple(params["filter_project_id"]), ("",))
        serializer = LeadDashboardRowsRequestSerializer(data={
            "date_start": "2026-01-01", "date_end": "2026-12-31",
            "project_ids": [""], "sort_by": "project_name",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["project_ids"], [""])
        path, count = export_leads_xlsx(filters)
        try:
            workbook = load_workbook(path, read_only=True)
            rows = list(workbook.active.iter_rows(max_col=13, values_only=True))
            workbook.close()
            self.assertEqual(count, 2)
            self.assertNotIn("Проект", rows[0])
            self.assertEqual(len(rows[0]), 13)
            self.assertTrue(all(len(row) == len(rows[0]) for row in rows[1:]))
        finally:
            path.unlink()

    def test_incremental_update_can_clear_project(self):
        client = Mock()
        client.iter_pages.return_value = [[{
            "ID": 1, "UF_CRM_1707131669360": None,
            "DATE_CREATE": self.now.isoformat(), "DATE_MODIFY": self.now.isoformat(),
        }]]
        load_leads(client)
        rebuild_lead_analytics()
        self.assertEqual(BitrixLeadAnalytics.objects.get(lead_id=1).project_id, "")
        self.assertEqual(BitrixLeadAnalytics.objects.get(lead_id=1).project_name, "")

    def test_comparison_periods_preserve_project_filter(self):
        query = LeadDashboardQuery(client=Mock())
        seen = []
        def dynamics(filters, dimension):
            seen.append(filters.project_ids)
            return []
        with patch.object(query, "dimension_dynamics", side_effect=dynamics), patch.object(query, "cards", return_value={}):
            query.build(self.filters(("2117", "")))
        self.assertTrue(seen)
        self.assertTrue(all(value == ("2117", "") for value in seen))
