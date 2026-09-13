from datetime import date, datetime, timezone
import sqlite3

from django.test import TestCase

from bitrix24.api.deal_views import rows_for
from bitrix24.models import BitrixLeadAnalytics
from bitrix24.services.dashboard_query import LeadDashboardFilters, LeadDashboardQuery
from bitrix24.services.deal_metrics import panel
from bitrix24.services.export import filtered_lead_analytics_queryset


class MissingSourceTests(TestCase):
    def setUp(self):
        self.rows = []
        for index, (source_id, source_name) in enumerate([
            ("", ""), ("old-1", ""), ("old-2", ""), ("web", "Website"),
        ], 1):
            created = datetime(2026, 2, 2, tzinfo=timezone.utc)
            BitrixLeadAnalytics.objects.create(lead_id=index, source_id=source_id,
                source_name=source_name, source_created_at=created, calculated_at=created)
            self.rows.append(dict(deal_id=index, source_id=source_id, source_name=source_name,
                source_created_at=created, result="P", category_id=0, amount=0,
                history_missing=False))
        self.filters = LeadDashboardFilters(date_start=date(2026, 1, 1), date_end=date(2026, 12, 31), exclude_untracked_department=False)

    def test_lead_missing_source_selection_and_other_group(self):
        selected = filtered_lead_analytics_queryset(self.filters, segment_type="source", segment_key="__missing_source__")
        self.assertEqual(set(selected.values_list("lead_id", flat=True)), {1, 2, 3})
        combined = filtered_lead_analytics_queryset(self.filters, segment_type="source", segment_keys=["__missing_source__", "web"])
        self.assertEqual(combined.count(), 4)
        named = filtered_lead_analytics_queryset(self.filters, segment_type="source", segment_key="web")
        self.assertEqual(list(named.values_list("lead_id", flat=True)), [4])

    def test_lead_grouping_combines_missing_source_codes(self):
        key, name, *_ = LeadDashboardQuery.DIMENSIONS["source"]
        with sqlite3.connect(":memory:") as db:
            db.create_function("if", 3, lambda condition, yes, no: yes if condition else no)
            db.execute("CREATE TABLE sources (source_id TEXT, source_name TEXT)")
            db.executemany("INSERT INTO sources VALUES (?, ?)", [(r["source_id"], r["source_name"]) for r in self.rows])
            sql = f'SELECT {key}, {name}, count(*) FROM sources GROUP BY 1, 2'.replace('if(', '"if"(')
            groups = db.execute(sql).fetchall()
        self.assertIn(("__missing_source__", "Источник не указан", 3), groups)
        self.assertEqual(len(groups), 2)

    def test_deal_summary_and_popup_use_same_missing_group(self):
        result = panel(self.rows, [], [], "sources", "month", {})
        missing = [row for row in result["summary"] if row["key"] == "__missing_source__"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["total"], 3)
        filters = dict(segment_type="sources", segment_key="__missing_source__", segment_keys=[], period=None, sort_by="deal_id", sort_direction="asc")
        selected = rows_for("deals", {"current": self.rows}, filters)
        self.assertEqual([row["deal_id"] for row in selected], [1, 2, 3])
