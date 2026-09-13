from datetime import date, datetime, timedelta
import re
import sqlite3
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from bitrix24.api.deal_views import DealReportView, rows_for
from bitrix24.services.crm_marts import MartReader, TABLE
from bitrix24.services.dashboard_query import UNTRACKED_DEPARTMENT_NAME, group_period_start, previous_comparison_date, previous_group_period
from bitrix24.services.deal_dashboard_query import DealDashboardQuery, PARTS
from bitrix24.services.deal_metrics import RESULT_NAMES, metrics, panel
from bitrix24.services.deal_repository import MOSCOW


class SumIf:
    def __init__(self): self.value = 0
    def step(self, value, condition): self.value += (value or 0) if condition else 0
    def finalize(self): return self.value


class CountIf(SumIf):
    def step(self, condition): super().step(1, condition)


class Average:
    def __init__(self): self.values = []
    def step(self, value):
        if value is not None: self.values.append(value)
    def finalize(self): return sum(self.values) / len(self.values) if self.values else None


class DealSqlClient:
    """Run report SQL on an isolated fixture, adapting ClickHouse scalar functions."""
    def __init__(self, rows):
        self.db = sqlite3.connect(":memory:")
        self.queries = []
        self.db.create_function("toString", 1, str)
        self.db.create_function("concat", -1, lambda *parts: "".join(parts))
        for function, group in (("toDate", "day"), ("toStartOfWeek", "week"), ("toStartOfMonth", "month"), ("toStartOfYear", "year")):
            self.db.create_function(function, -1, lambda value, *args, group=group: group_period_start(date.fromisoformat(value[:10]), group).isoformat())
        self.db.create_aggregate("countIf", 1, CountIf)
        self.db.create_aggregate("sumIf", 2, SumIf)
        self.db.create_aggregate("avgOrNull", 1, Average)
        fields = [key for key in rows[0] if key != "deal_id"]
        self.db.execute("CREATE TABLE deals (" + ", ".join(fields) + ")")
        self.db.executemany("INSERT INTO deals VALUES (" + ",".join("?" for _ in fields) + ")", [
            tuple(self.bind(row[key]) for key in fields) for row in rows
        ])

    @staticmethod
    def bind(value):
        if isinstance(value, datetime): return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.isoformat() if isinstance(value, date) else value

    def execute(self, sql, args=None, with_column_types=False):
        self.queries.append(sql)
        if sql.startswith("SELECT engine"):
            return [("MergeTree", "fixture")]
        values = []
        def substitute(match):
            value = (args or {})[match.group(1)]
            if isinstance(value, (list, tuple)):
                values.extend(self.bind(item) for item in value)
                return "(" + ",".join("?" for _ in value) + ")"
            values.append(self.bind(value))
            return "?"
        sql = re.sub(r"%\((\w+)\)s", substitute, sql.replace(TABLE, "deals"))
        sql = re.sub(r"\bif\(", "iif(", sql)
        cursor = self.db.execute(sql, values)
        columns = [column[0] for column in cursor.description]
        rows = []
        for values in cursor.fetchall():
            row = list(values)
            for index, key in enumerate(columns):
                if key == "period": row[index] = date.fromisoformat(row[index])
                elif key in ("source_created_at", "speed_calculated_at") and row[index]:
                    row[index] = datetime.fromisoformat(row[index]).replace(tzinfo=MOSCOW)
                elif row[index] is None and key in ("amount", "return_customers"):
                    row[index] = 0
            rows.append(tuple(row))
        return (rows, [(key, "fixture") for key in columns]) if with_column_types else rows


class DealDashboardQueryTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.rows = []
        for index, day in enumerate(["2024-02-29", "2025-01-02", "2025-02-03", "2025-02-15", "2025-03-01", "2025-12-29",
                                     "2026-01-02", "2026-02-02", "2026-02-03", "2026-02-05", "2026-02-15", "2026-03-01"], 1):
            result = ("S", "F", "P", "?")[index % 4]
            category = index % 2
            manager = (0, 10, 20)[index % 3]
            source = ("", "web", "unknown-code")[index % 3]
            created = datetime.fromisoformat(day).replace(tzinfo=MOSCOW)
            self.rows.append(dict(entity_id=index, deal_id=index, lead_id=index if index % 2 else 0,
                title=f"Deal {index}", category_id=category, category_name=f"Funnel {category}",
                stage_id=result, stage_key=f"{category}:{result}", stage_name=result, result=result,
                result_name=RESULT_NAMES[result], manager_id=manager, assigned_by_id=manager,
                manager_name=f"Manager {manager}", department_name="Sales", source_id=source,
                source_name="Website" if source == "web" else "", amount=index * 125.25,
                history_missing=index % 2, is_return_customer=None if index % 3 == 0 else bool(index % 2),
                source_created_at=created, speed_calculated_at=created + timedelta(days=2),
                processing_duration_days=None if index % 3 == 0 else 2.5,
                deal_type_name="Type", activity_name="Activity"))
        self.client = DealSqlClient(self.rows)
        self.addCleanup(self.client.db.close)
        self.mart = object.__new__(MartReader)
        self.mart.client, self.mart.table, self.mart.snapshot, self.mart.legacy = self.client, TABLE, "fixture", False
        self.mart.refs = {"tracking": {10: {"department_name": "Sales"}, 20: {"department_name": "Sales"}},
                          "categories": [], "stages": {}, "sources": [], "users": {}}
        self.query = DealDashboardQuery(self.mart)
        self.filters = dict(date_start=date(2026, 1, 1), date_end=date(2026, 3, 31), group_by="month",
                            exclude_untracked_department=False)

    def assertEquivalent(self, expected, actual):
        if isinstance(expected, dict):
            for key in expected:
                # Older raw-row aggregation picked an arbitrary category for mixed-category groups.
                if key != "category_id": self.assertEquivalent(expected[key], actual[key])
        elif isinstance(expected, list):
            self.assertEqual(len(expected), len(actual))
            for left, right in zip(expected, actual): self.assertEquivalent(left, right)
        elif isinstance(expected, float): self.assertAlmostEqual(expected, actual, places=7)
        else: self.assertEqual(expected, actual)

    def test_aggregates_match_existing_metrics_for_every_grouping(self):
        for group in ("day", "week", "month", "year"):
            with self.subTest(group=group):
                filters = {**self.filters, "group_by": group}
                old_start, old_end = [previous_comparison_date(filters[key], group) for key in ("date_start", "date_end")]
                start = group_period_start(filters["date_start"], group)
                ranges = [(filters["date_start"], filters["date_end"]), (old_start, old_end), (previous_group_period(start, group), start - timedelta(days=1))]
                current, previous, prior = [[row for row in self.rows if lo <= row["source_created_at"].date() <= hi] for lo, hi in ranges]
                report = self.query.build(filters)
                self.assertEquivalent(metrics(current), report["cards"])
                for kind in PARTS:
                    self.assertEquivalent(panel(current, previous, prior, kind, group, {}), report[kind])

    def test_detail_selection_summary_and_pagination(self):
        for kind, key in (("sources", "__missing_source__"), ("managers", "__unassigned__"), ("results", "S"), ("loss-reasons", "")):
            filters = {**self.filters, "segment_type": kind, "segment_key": key, "segment_keys": [],
                       "period": None, "sort_by": "deal_id", "sort_direction": "asc"}
            current = [row for row in self.rows if self.filters["date_start"] <= row["source_created_at"].date() <= self.filters["date_end"]]
            expected = rows_for("deals", {"current": current}, filters)
            summary = self.query.detail_summary(filters)
            self.assertEqual(summary["total"], len(expected))
            self.assertEqual(summary["amount"], sum(row["amount"] for row in expected))
            page = self.query.detail_rows(filters, limit=1, offset=1)
            self.assertEqual([row["deal_id"] for row in page], [row["deal_id"] for row in expected[1:2]])
            self.assertEqual([row["deal_id"] for row in self.query.export_rows(filters, batch_size=1)], [row["deal_id"] for row in expected])

    def test_untracked_managers_and_related_filters(self):
        filters = {**self.filters, "tracked_manager_ids": [10], "department_names": [UNTRACKED_DEPARTMENT_NAME],
                   "category_ids": [0], "lead_link": "all", "results": ["S", "P"]}
        rows = self.query.aggregates(filters, "managers")
        expected = [row for row in self.rows if self.filters["date_start"] <= row["source_created_at"].date() <= self.filters["date_end"]
                    and row["manager_id"] != 10 and row["category_id"] == 0 and row["result"] in ("S", "P")]
        self.assertEqual(sum(row["total"] for row in rows), len(expected))

    def test_warm_report_uses_only_snapshot_checks(self):
        user = Mock(is_authenticated=True)
        request = APIRequestFactory().post("/", {"date_start": "2026-01-01", "date_end": "2026-03-31",
            "category_ids": [], "exclude_untracked_department": False, "use_personal_departments": False}, format="json")
        force_authenticate(request, user=user)
        with patch("bitrix24.api.deal_views._can_view_crm", return_value=True), patch("bitrix24.api.deal_views.manager_options", return_value=[]), patch(
            "bitrix24.api.deal_views.reader", side_effect=lambda: self.mart
        ):
            first = DealReportView.as_view()(request, section="deals", part="report")
            self.assertEqual(first.status_code, 200)
            self.client.queries.clear()
            second = DealReportView.as_view()(request, section="deals", part="report")
        self.assertEqual(first.data, second.data)
        self.assertTrue(self.client.queries)
        self.assertTrue(all(sql.startswith("SELECT engine") for sql in self.client.queries))
        self.assertNotIn("current", second.data)
        self.assertNotIn("refs", second.data)
