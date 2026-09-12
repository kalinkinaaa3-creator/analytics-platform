from datetime import date
from dataclasses import replace
import re
import sqlite3

from django.test import SimpleTestCase, TestCase

from bitrix24.api.views import LeadDashboardFiltersView
from bitrix24.models import BitrixLeadAnalytics
from bitrix24.services.crm_marts import MartReader, TABLE
from bitrix24.services.dashboard_query import LeadDashboardFilters, LeadDashboardQuery, UNTRACKED_DEPARTMENT_NAME
from bitrix24.services.export import filtered_lead_analytics_queryset


class FacetSqlClient:
    """Execute the mart's SELECT DISTINCT facet queries against a small SQL fixture."""
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE entities (entity_type TEXT, source_created_at TEXT, manager_id INTEGER, category_id INTEGER, stage_key TEXT, result TEXT, source_id TEXT, lead_id INTEGER)")
        self.db.executemany("INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            ("deal", "2026-02-02", 10, 0, "0:WON", "S", "web", 1),
            ("deal", "2026-02-02", 20, 2, "2:NEW", "P", "phone", 0),
            ("deal", "2026-02-02", 30, 0, "0:NEW", "P", "web", 2),
        ])

    def execute(self, sql, args):
        values = []
        def bind(match):
            value = args[match.group(1)]
            if isinstance(value, (tuple, list)):
                values.extend(value)
                return "(" + ",".join("?" for _ in value) + ")"
            values.append(value.isoformat() if hasattr(value, "isoformat") else value)
            return "?"
        sql = re.sub(r"%\((\w+)\)s", bind, sql.replace(TABLE, "entities"))
        return self.db.execute(sql, values).fetchall()


class DealFacetTests(SimpleTestCase):
    def setUp(self):
        self.mart = object.__new__(MartReader)
        self.mart.client = FacetSqlClient()
        self.addCleanup(self.mart.client.db.close)
        self.mart.refs = {
            "tracking": {10: {"department_name": "Sales"}, 20: {"department_name": "Sales"}, 30: {"department_name": "Support"}},
            "users": {key: {"full_name": str(key)} for key in (10, 20, 30)},
            "categories": [{"category_id": 0}, {"category_id": 2}],
            "stages": {key: {"key": key, "category_sort": 0, "category_id": int(key[0]), "sort": 0} for key in ("0:WON", "0:NEW", "2:NEW")},
            "sources": [{"source_id": "web", "source_name": "Web"}, {"source_id": "phone", "source_name": "Phone"}],
        }
        self.filters = {"date_start": date(2026, 1, 1), "date_end": date(2026, 12, 31), "tracked_manager_ids": [10, 30], "exclude_untracked_department": True}

    def test_unchecked_manager_appears_under_untracked_department(self):
        opts = self.mart.options(self.filters, personal_manager_ids=[10, 30])
        self.assertIn({"department_name": UNTRACKED_DEPARTMENT_NAME}, opts["departments"])
        self.assertEqual({row["source_id"] for row in opts["sources"]}, {"web"})
        self.assertEqual({row["manager_id"] for row in opts["managers"]}, {10, 30})

    def test_selecting_untracked_links_managers_sources_categories_and_results(self):
        opts = self.mart.options({**self.filters, "department_names": [UNTRACKED_DEPARTMENT_NAME], "exclude_untracked_department": False})
        self.assertEqual([row["manager_id"] for row in opts["managers"]], [20])
        self.assertEqual([row["source_id"] for row in opts["sources"]], ["phone"])
        self.assertEqual([row["category_id"] for row in opts["categories"]], [2])
        self.assertEqual([row["id"] for row in opts["results"]], ["P"])

    def test_department_selection_excludes_unchecked_colleague(self):
        opts = self.mart.options({**self.filters, "department_names": ["Sales"]})
        self.assertEqual([row["manager_id"] for row in opts["managers"]], [10])

    def test_other_filters_still_limit_department_choices(self):
        opts = self.mart.options({**self.filters, "source_ids": ["phone"]}, personal_manager_ids=[10, 30])
        self.assertEqual(opts["departments"], [{"department_name": UNTRACKED_DEPARTMENT_NAME}])
        self.assertEqual(opts["managers"], [])

    def test_no_tracked_managers_does_not_mean_all_managers(self):
        opts = self.mart.options({**self.filters, "tracked_manager_ids": []}, personal_manager_ids=[])
        self.assertEqual(opts["managers"], [])
        self.assertEqual(opts["sources"], [])
        self.assertEqual(opts["departments"], [{"department_name": UNTRACKED_DEPARTMENT_NAME}])


class LeadFacetTests(TestCase):
    def setUp(self):
        for key, source in [(10, "web"), (20, "phone")]:
            BitrixLeadAnalytics.objects.create(lead_id=key, manager_id=key, department_name="Sales", source_id=source, dashboard_status="target", source_created_at="2026-02-02T00:00:00Z", calculated_at="2026-02-02T00:00:00Z")
        self.filters = LeadDashboardFilters(date_start=date(2026, 1, 1), date_end=date(2026, 12, 31), source_ids=("web",))

    def test_personal_manager_selection_limits_other_facets(self):
        rows = LeadDashboardFiltersView._option_rows(self.filters, "source_ids", [10])
        self.assertEqual(set(rows.values_list("source_id", flat=True)), {"web"})
        managers = LeadDashboardFiltersView._option_rows(self.filters, "manager_ids", [20])
        self.assertFalse(managers.exists())

    def test_department_facet_remains_available_for_changing_personal_selection(self):
        rows = LeadDashboardFiltersView._option_rows(self.filters, "department_names", [])
        self.assertEqual(list(rows.values_list("department_name", flat=True)), ["Sales"])

    def test_empty_personal_selection_returns_no_sources(self):
        rows = LeadDashboardFiltersView._option_rows(self.filters, "source_ids", [])
        self.assertFalse(rows.exists())

    def test_unchecked_lead_manager_is_in_untracked_group(self):
        filters = replace(self.filters, source_ids=(), department_names=(UNTRACKED_DEPARTMENT_NAME,), tracked_manager_ids=(10,), exclude_untracked_department=False)
        self.assertEqual(list(filtered_lead_analytics_queryset(filters).values_list("manager_id", flat=True)), [20])
        source_rows = LeadDashboardFiltersView._option_rows(filters, "source_ids")
        self.assertEqual(list(source_rows.values_list("source_id", flat=True)), ["phone"])
        department_rows = LeadDashboardFiltersView._option_rows(filters, "department_names")
        self.assertEqual(set(department_rows.values_list("effective_department_name", flat=True)), {"Sales", UNTRACKED_DEPARTMENT_NAME})

    def test_normal_lead_department_excludes_unchecked_colleague(self):
        filters = replace(self.filters, source_ids=(), department_names=("Sales",), tracked_manager_ids=(10,))
        self.assertEqual(list(filtered_lead_analytics_queryset(filters).values_list("manager_id", flat=True)), [10])

    def test_clickhouse_scope_and_detail_scope_use_same_personal_group(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.create_function("if", 3, lambda condition, yes, no: yes if condition else no)
        db.execute("CREATE TABLE leads (manager_id INTEGER, department_name TEXT, source_created_at TEXT)")
        db.executemany("INSERT INTO leads VALUES (?, ?, ?)", [(10, "Sales", "2026-02-02"), (20, "Sales", "2026-02-02"), (None, "Unknown", "2026-02-02")])
        for departments, expected in [(("Sales",), {10}), ((UNTRACKED_DEPARTMENT_NAME,), {20, None}), (("Sales", UNTRACKED_DEPARTMENT_NAME), {10, 20, None})]:
            with self.subTest(departments=departments):
                filters = replace(self.filters, source_ids=(), department_names=departments, tracked_manager_ids=(10,), exclude_untracked_department=False)
                where, args = LeadDashboardQuery._where(filters)
                values = []
                def bind(match):
                    value = args[match.group(1)]
                    if isinstance(value, tuple):
                        values.extend(value)
                        return "(" + ",".join("?" for _ in value) + ")"
                    values.append(value.isoformat() if hasattr(value, "isoformat") else value)
                    return "?"
                sql = re.sub(r"%\((\w+)\)s", bind, "SELECT manager_id FROM leads WHERE " + where)
                self.assertEqual({row[0] for row in db.execute(sql, values)}, expected)
