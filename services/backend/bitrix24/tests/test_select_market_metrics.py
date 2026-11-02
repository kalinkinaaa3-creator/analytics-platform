"""Run dimension aggregation against fixtures without a live ClickHouse server."""
import re
import sqlite3
from datetime import date
from unittest import TestCase

from bitrix24.services.dashboard_query import LeadDashboardFilters, LeadDashboardQuery


class DimensionMetricsTests(TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.create_function("toStartOfMonth", 1, lambda value: value[:7] + "-01")
        self.db.create_function("toString", 1, lambda value: str(value))
        self.db.execute("CREATE TABLE leads (source_created_at TEXT, source_id TEXT, source_name TEXT, manager_id INTEGER, manager_name TEXT, dashboard_status TEXT, is_return_customer INTEGER)")
        for year, counts in ((2026, {"target": 2, "apm": 3, "low_quality": 5, "in_progress": 7}),
                             (2025, {"target": 1, "apm": 1, "low_quality": 2})):
            for status, count in counts.items():
                self.db.executemany("INSERT INTO leads VALUES (?, 'web', 'Website', 1, 'Manager', ?, 0)", [(f"{year}-01-15", status)] * count)
        self.query = LeadDashboardQuery(client=self)

    def execute(self, sql, params, with_column_types=False):
        # Translate dialect functions only; execute the production aggregation.
        sql = sql.replace("default.bitrix_lead_analytics", "leads").replace("countIf(", "SUM(")
        sql = sql.replace("USING period", "USING (period)")
        sql = re.sub(r"\bif\(", "IIF(", sql)
        sql = re.sub(r"%\((\w+)\)s", r":\1", sql)
        cursor = self.db.execute(sql, {key: value.isoformat() if isinstance(value, date) else value for key, value in params.items()})
        return cursor.fetchall(), [(item[0], "") for item in cursor.description]

    def test_sources_and_managers_include_transferred_in_both_periods(self):
        for dimension in ("source", "manager"):
            with self.subTest(dimension=dimension):
                periods = [self.query.dimension_dynamics(LeadDashboardFilters(date(year, 1, 1), date(year, 1, 31), exclude_untracked_department=False), dimension) for year in (2026, 2025)]
                self.assertEqual(periods[0][0]["dimension_target"], 5)
                self.assertEqual(periods[0][0]["conversion"], 50)
                self.assertEqual(periods[0][0]["value"], 17)
                self.assertEqual(periods[1][0]["conversion"], 50)
                summary = self.query._summarize_dimensions(*periods)[0]
                self.assertEqual(summary["dimension_target"], 5)
                self.assertEqual(summary["previous_year_dimension_target"], 2)

    def test_status_dynamics_preserve_separate_target_and_transferred_groups(self):
        rows = self.query.dimension_dynamics(LeadDashboardFilters(date(2026, 1, 1), date(2026, 1, 31), exclude_untracked_department=False), "dashboard_status")
        by_status = {row["dimension_key"]: row for row in rows}
        self.assertEqual(by_status["target"]["dimension_target"], 2)
        self.assertEqual(by_status["apm"]["dimension_target"], 0)
        self.assertEqual(by_status["apm"]["value"], 3)
