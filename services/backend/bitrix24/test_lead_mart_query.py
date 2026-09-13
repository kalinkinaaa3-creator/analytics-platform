from dataclasses import replace
from datetime import date, datetime
from unittest.mock import Mock, patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from bitrix24.models import BitrixLeadAnalytics
from bitrix24.api.views import LeadDashboardRowsView
from bitrix24.services.clickhouse import COLUMNS, TABLE_NAME
from bitrix24.services.crm_marts import TABLE, SnapshotChanged
from bitrix24.services.dashboard_query import LeadDashboardFilters, UNTRACKED_DEPARTMENT_NAME
from bitrix24.services.export import filtered_lead_analytics_queryset
from bitrix24.services.lead_mart_query import PublishedLeadQuery
from bitrix24.test_deal_dashboard_query import DealSqlClient


class Sum:
    def __init__(self):
        self.value = None
    def step(self, value):
        if value is not None:
            self.value = (self.value or 0) + value
    def finalize(self):
        return self.value


class LeadSqlClient(DealSqlClient):
    def __init__(self, rows):
        super().__init__(rows)
        self.db.create_function("toString", 1, lambda value: None if value is None else str(value))
        self.db.create_aggregate("sumOrNull", 1, Sum)
        self.snapshot = "published-leads"

    def execute(self, sql, args=None, **kwargs):
        if sql.startswith("SELECT toString(uuid)"):
            return [(self.snapshot,)]
        return super().execute(sql.replace(TABLE_NAME, TABLE), args, **kwargs)


class PublishedLeadQueryTests(TestCase):
    def setUp(self):
        stamp = datetime.fromisoformat("2026-02-02T00:00:00+03:00")
        for index, manager in enumerate((10, 20, None), 1):
            BitrixLeadAnalytics.objects.create(lead_id=index, manager_id=manager, manager_name=str(manager),
                department_name="Sales", source_id="web" if index == 1 else "", source_name="Web" if index == 1 else "",
                status_id="NEW" if index == 1 else "LOSE", status_name="New" if index == 1 else "Lost",
                status_semantic_id="P" if index == 1 else "F", dashboard_status="in_progress" if index == 1 else "low_quality",
                is_low_quality=index != 1, source_created_at=stamp, calculated_at=stamp,
                is_return_customer=index == 1, opportunity=index * 125, processing_duration_days=index)
        values = []
        for item in BitrixLeadAnalytics.objects.order_by("lead_id"):
            row = {key: getattr(item, key) for key in COLUMNS}
            for key in ("opportunity", "processing_duration_days"):
                row[key] = float(row[key]) if row[key] is not None else None
            values.append(row)
        self.client = LeadSqlClient(values)
        self.addCleanup(self.client.db.close)
        self.query = PublishedLeadQuery(self.client)
        self.filters = LeadDashboardFilters(date_start=date(2026, 1, 1), date_end=date(2026, 12, 31), exclude_untracked_department=False)

    def test_detail_selection_matches_previous_queryset(self):
        for kind, key in [(None, ""), ("source", "__missing_source__"), ("manager", "__unassigned__"), ("dashboard_status", "low_quality"), ("low_quality_status", "LOSE")]:
            options = dict(segment_type=kind, segment_key=key, sort_by="lead_id", sort_direction="asc")
            with self.subTest(kind=kind):
                old = filtered_lead_analytics_queryset(self.filters, **options)
                expected = list(old.values_list("lead_id", flat=True))
                rows = self.query.detail_rows(self.filters, options)
                self.assertEqual([row["lead_id"] for row in rows], expected)
                self.assertEqual(self.query.detail_summary(self.filters, options)["total"], len(expected))
                self.assertEqual([row.lead_id for row in self.query.export_rows(self.filters, options, batch_size=1)], expected)

    def test_paging_period_and_empty_summary(self):
        options = dict(sort_by="lead_id", sort_direction="desc", period=date(2026, 2, 1))
        self.assertEqual(self.query.detail_rows(self.filters, options, limit=1, offset=1)[0]["lead_id"], 2)
        options["period"] = date(2026, 3, 1)
        summary = self.query.detail_summary(self.filters, options)
        self.assertEqual(summary["total"], 0)
        self.assertIsNone(summary["processing_duration_days"])

    def test_facets_use_published_data_and_personal_selection(self):
        filters = replace(self.filters, tracked_manager_ids=(10,))
        # The raw/model table can change without changing the published options.
        BitrixLeadAnalytics.objects.all().delete()
        options = self.query.options(filters, personal_ids=[10])
        self.assertEqual(options["sources"], [{"source_id": "web", "source_name": "Web", "lead_count": 1}])
        self.assertEqual({row["department_name"] for row in options["departments"]}, {"Sales", UNTRACKED_DEPARTMENT_NAME})
        self.assertEqual(self.query.options(filters, personal_ids=[])["sources"], [])

    def test_changed_snapshot_is_rejected(self):
        self.client.snapshot = "new-leads"
        with self.assertRaises(SnapshotChanged):
            self.query.check()

    def test_rows_endpoint_uses_published_data_and_rejects_snapshot_change(self):
        BitrixLeadAnalytics.objects.all().delete()
        request = APIRequestFactory().post("/", {"date_start": "2026-01-01", "date_end": "2026-12-31",
            "use_personal_departments": False, "exclude_untracked_department": False}, format="json")
        force_authenticate(request, user=Mock(is_authenticated=True))
        with patch("bitrix24.api.views._can_view_crm", return_value=True), patch("bitrix24.api.views.selected_manager_ids", return_value=[10]), patch(
            "bitrix24.api.views.display_names", return_value={10: "Display"}
        ), patch("bitrix24.api.views.PublishedLeadQuery", return_value=self.query):
            response = LeadDashboardRowsView.as_view()(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["total"], 3)
            self.assertEqual(response.data["snapshot"], "published-leads")
            self.assertEqual(response.data["items"][0]["department_name"], "Display")
            self.client.snapshot = "new-leads"
            self.assertEqual(LeadDashboardRowsView.as_view()(request).status_code, 409)
