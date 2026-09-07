"""Offline regression checks for scheduled refresh health and future plans."""
from datetime import date, timedelta
import json
import logging
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from tests.test_load_notifications import isolated_function


class ContextHealthTests(unittest.TestCase):
    def check_day(self, today, latest_fact, status="success", failed_requests=0):
        yesterday = today - timedelta(days=1)
        stats = dict(performance_rows=10, criteria_rows=10, visitor_rows=10,
                     date_from=(yesterday - timedelta(days=13)).isoformat(),
                     date_to=yesterday.isoformat())
        cursor = Mock()
        cursor.fetchone.return_value = (1, status, today, today, json.dumps(stats), "",
                                       today, today)

        def scalar(_cursor, sql, params=None):
            if "success = FALSE" in sql:
                return failed_requests
            if "MAX(" in sql:
                return today
            return 1

        def execute(sql, params=None):
            if sql.startswith("EXISTS"):
                return [(1,)]
            if "count(), max(date)" in sql:
                return [(10, latest_fact, today)]
            return [(0, 0, 0, 0)]

        client_module = ModuleType("analytics.clickhouse.client")
        client_module.get_clickhouse_client = Mock(return_value=Mock(execute=execute))
        namespace = dict(date=date, timedelta=timedelta, json=json,
                         DEFAULT_INCREMENTAL_DAYS=14, scalar=scalar,
                         table_exists=lambda *args: True, logger=logging.getLogger("test"))
        check = isolated_function("datasets/management/commands/check_table_health.py",
                                  "check_context_analytics_health", namespace)
        problems, ok = [], []
        with patch.dict(sys.modules, {"analytics.clickhouse.client": client_module}):
            check(cursor, today, problems, ok)
        return problems, ok

    def test_empty_weekends_are_allowed_on_sunday_and_monday(self):
        for today in (date(2026, 9, 6), date(2026, 9, 7)):
            with self.subTest(today=today):
                problems, ok = self.check_day(today, date(2026, 9, 4))
                self.assertEqual(problems, [])
                self.assertTrue(ok)

    def test_weekday_gaps_and_stale_friday_are_still_errors(self):
        for today, fact in ((date(2026, 9, 8), date(2026, 9, 4)),
                            (date(2026, 9, 7), date(2026, 9, 3))):
            self.assertTrue(self.check_day(today, fact)[0])

    def test_weekend_does_not_hide_failed_run_or_api_errors(self):
        for kwargs in ({"status": "failed"}, {"failed_requests": 1}):
            self.assertTrue(self.check_day(date(2026, 9, 7), date(2026, 9, 4), **kwargs)[0])


class FuturePlanTests(unittest.TestCase):
    def test_future_full_weeks_pass_backend_filters(self):
        normalize = isolated_function("lead_generation/services.py", "normalize_filters",
                                      dict(date=date, MIN_WEEK=date(2024, 12, 30)))
        result = normalize({"week_from": "2027-01-04", "week_to": "2027-01-18"})
        self.assertEqual(result["week_to"], date(2027, 1, 18))
        with self.assertRaises(ValueError):
            normalize({"week_from": "2027-01-05", "week_to": "2027-01-18"})
