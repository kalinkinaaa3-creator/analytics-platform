"""Offline demand math/publication tests. No live databases, API calls or writes."""
import os
import unittest
from datetime import date
from unittest.mock import Mock, patch

os.environ["DJANGO_SETTINGS_MODULE"] = "tests.wordstat_settings"
import django
django.setup()

from analytics.services.wordstat_demand import (
    build_demand, cached_demand, complete_sum, describe_slices, metrics, season_profile, shift, unpack_facts,
)
from analytics.services.wordstat_demand_mart import publish_rows

TODAY = date(2026, 9, 6)


def source(phrases=None):
    rows = []
    for phrase, feature, category, value in phrases or [("a", "A", "AA", 100), ("b", "A", "AB", 900)]:
        for year in range(2023, 2027):
            for month in range(1, 13):
                rows.append((feature, category, phrase, date(year, month, 1), value, "fixture"))
    return unpack_facts(rows, TODAY)


class DemandMathTests(unittest.TestCase):
    def test_zero_is_distinct_from_missing(self):
        self.assertEqual(complete_sum([0, 0]), 0)
        self.assertIsNone(complete_sum([0, None]))
        self.assertEqual(metrics(40, 0)["status"], "new")
        self.assertIsNone(metrics(40, 0)["growth_percent"])
        self.assertEqual(metrics(None, 0)["status"], "missing")

    def test_neutral_threshold_boundaries(self):
        self.assertEqual(metrics(102, 100)["status"], "stable")
        self.assertEqual(metrics(98, 100)["status"], "stable")
        self.assertEqual(metrics(103, 100)["status"], "growth")
        self.assertEqual(metrics(97, 100)["status"], "decline")

    def test_month_shift_and_rolling_comparison(self):
        self.assertEqual(shift(date(2026, 1, 1), -1), date(2025, 12, 1))
        for length in (1, 3, 6, 12):
            r = build_demand(dict(period_months=length), TODAY, source())
            self.assertEqual(r["summary"]["current_volume"], length * 1000)
            self.assertEqual(r["period"]["end_month"], "2026-08")
            self.assertEqual(r["period"]["previous_end"], "2025-08-31")
        self.assertEqual(r["period"]["current_start"], "2025-09-01")
        self.assertEqual(r["period"]["previous_start"], "2024-09-01")

    def test_aggregate_growth_is_weighted_by_volume(self):
        refs, facts, snapshot = source()
        facts["a"][date(2026, 8, 1)] = 200
        r = build_demand(dict(period_months=1), TODAY, (refs, facts, snapshot))
        self.assertEqual(r["items"][0]["growth_percent"], 10)
        self.assertEqual(r["items"][0]["children"]["growth"]["share"], 50)

    def test_duplicate_is_not_added_to_volume(self):
        row = ("A", "AA", "a", date(2025, 1, 1), 100, "s")
        _, facts, _ = unpack_facts([row, row], TODAY)
        self.assertIsNone(facts["a"][date(2025, 1, 1)])

    def test_current_month_is_never_available(self):
        r = build_demand({}, TODAY, source())
        self.assertNotIn("2026-09", r["available_months"])

    def test_missing_month_does_not_become_zero(self):
        refs, facts, snap = source()
        facts["b"][date(2026, 8, 1)] = None
        r = build_demand(dict(end_month=date(2026, 8, 1), period_months=1), TODAY, (refs, facts, snap))
        self.assertIsNone(r["summary"]["current_volume"])
        self.assertEqual(r["latest_month"], "2026-07")
        self.assertIn("2026-08", r["available_months"])
        self.assertEqual(r["month_coverage"]["2026-08"], "partial")

    def test_other_category_gap_does_not_hide_complete_selected_month(self):
        refs, facts, snap = source([("a", "A", "AA", 100), ("b", "B", "BB", 200)])
        facts["b"][date(2026, 8, 1)] = None
        r = build_demand(dict(feature="A", period_months=1), TODAY, (refs, facts, snap))
        self.assertEqual(r["latest_month"], "2026-08")
        self.assertEqual(r["summary"]["current_volume"], 100)

    def test_missing_current_year_still_has_completed_calendar_months(self):
        refs, facts, snap = source()
        facts = {p: {d: v for d, v in days.items() if d.year < 2026} for p, days in facts.items()}
        r = build_demand({}, TODAY, (refs, facts, snap))
        self.assertEqual(r["month_coverage"]["2026-08"], "missing")
        self.assertEqual(r["latest_month"], "2025-12")

    def test_hierarchy_and_same_named_subcategories(self):
        data = source([("a", "A", "same", 100), ("b", "B", "same", 200)])
        r = build_demand(dict(level="category"), TODAY, data)
        self.assertEqual(len({i["id"] for i in r["items"]}), 2)
        r = build_demand(dict(level="phrase", feature="B", category="same"), TODAY, data)
        self.assertEqual([i["phrase"] for i in r["items"]], ["b"])

    def test_focus_does_not_change_list_summary(self):
        r = build_demand(dict(level="phrase", phrase="a", period_months=1), TODAY, source())
        self.assertEqual(r["summary"]["current_volume"], 1000)
        self.assertEqual(r["summary"]["count"], 2)

    def test_seasonality_independent_of_period(self):
        a = build_demand(dict(period_months=1), TODAY, source())
        b = build_demand(dict(period_months=12, end_month=date(2025, 6, 1)), TODAY, source())
        self.assertEqual(a["seasonality"], b["seasonality"])
        self.assertEqual(a["seasonality"][0]["years"], [2023, 2024, 2025])
        self.assertEqual(a["seasonality"][0]["coefficients"], [1] * 12)

    def test_incomplete_and_zero_years_excluded_from_season(self):
        monthly = {date(2025, m, 1): 0 for m in range(1, 13)}
        monthly[date(2024, 1, 1)] = 10
        self.assertEqual(season_profile(monthly, TODAY)["years"], [])

    def test_slice_shares_percentage_points_and_parent(self):
        current, previous = [date(2026, 8, 1)], [date(2025, 8, 1)]
        values = {("focus", "device", "phone", current[0]): 70,
                  ("focus", "device", "phone", previous[0]): 60,
                  ("parent", "device", "phone", current[0]): 100}
        result = describe_slices(values, "device", [("phone", "Phone")], metrics(100, 100), metrics(200, 200), current, previous, 10)
        item = result["items"][0]
        self.assertEqual(item["share"], 70)
        self.assertEqual(item["change_pp"], 10)
        self.assertEqual(item["difference_vs_parent_pp"], 20)
        self.assertEqual(result["other_share"], 30)

    def test_inconsistent_slice_is_not_displayed_as_complete_structure(self):
        day = date(2026, 8, 1)
        result = describe_slices({("focus", "device", "phone", day): 101}, "device", [("phone", "Phone")], metrics(100, 100), metrics(None, None), [day], [date(2025, 8, 1)], 10)
        self.assertFalse(result["consistent"])
        self.assertIsNone(result["leader"])
        self.assertEqual(result["reason"], "inconsistent")

    def test_slice_diagnostics_distinguish_gaps_from_zero_totals(self):
        day = date(2026, 8, 1)
        for total, reason in [(None, "missing_total"), (0, "zero_total"), (100, "missing_slices")]:
            r = describe_slices({}, "device", [("phone", "Phone")], metrics(total, 100), metrics(None, None), [day], [shift(day, -12)], 10)
            self.assertEqual(r["reason"], reason)
            self.assertEqual(r["items"][0]["missing_months"], ["2026-08"])


class CacheTests(unittest.TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_cache_reuse_and_publication_change(self):
        with patch("analytics.services.wordstat_demand.demand_snapshot", return_value="one") as version, patch(
                "analytics.services.wordstat_demand.build_demand", return_value={"snapshot": "one"}) as build:
            cached_demand({})
            cached_demand({})
            self.assertEqual(build.call_count, 1)
            version.return_value = "two"
            build.return_value = {"snapshot": "two"}
            self.assertEqual(cached_demand({})["snapshot"], "two")
            self.assertEqual(build.call_count, 2)

    def test_publication_race_retries_instead_of_caching_mixed_report(self):
        with patch("analytics.services.wordstat_demand.demand_snapshot", side_effect=["one", "two", "two", "two"]), patch(
                "analytics.services.wordstat_demand.build_demand", side_effect=[{"snapshot": "one"}, {"snapshot": "two"}]) as build:
            self.assertEqual(cached_demand({})["snapshot"], "two")
            self.assertEqual(build.call_count, 2)


class PublicationTests(unittest.TestCase):
    def client(self, fail=None):
        client = Mock()
        inserted = []
        def execute(sql, rows=None):
            if sql.startswith("SELECT engine"):
                return [("Atomic",)]
            if sql.startswith("INSERT"):
                if fail == "insert":
                    raise RuntimeError("insertion failed")
                inserted.extend(rows)
            if sql.startswith("SELECT count(),"):
                return [(len(inserted), sum(r[6] or 0 for r in inserted) + (1 if fail == "sum" else 0), sum(r[6] is not None for r in inserted))]
            if sql.startswith("SELECT count() FROM"):
                return [(1 if fail == "duplicate" else 0,)]
        client.execute.side_effect = execute
        return client

    def rows(self):
        return [("all", "", "A", "AA", "a", date(2025, 1, 1), 10),
                ("device", "phone", "A", "AA", "a", date(2025, 1, 1), 7)]

    def test_verified_publication_exchanges_only_new_mart(self):
        client = self.client()
        self.assertEqual(publish_rows(client, self.rows())["rows"], 2)
        sql = [call.args[0] for call in client.execute.call_args_list]
        self.assertEqual(sum(q.startswith("EXCHANGE") for q in sql), 1)
        self.assertFalse(any("yd_wordstat_for" in q or "TRUNCATE" in q for q in sql))

    def test_failed_staging_never_replaces_published_mart(self):
        for failure in ("insert", "sum", "duplicate"):
            with self.subTest(failure=failure):
                client = self.client(failure)
                with self.assertRaises((RuntimeError, ValueError)):
                    publish_rows(client, self.rows())
                self.assertFalse(any(call.args[0].startswith("EXCHANGE") for call in client.execute.call_args_list))

    def test_empty_mart_does_not_replace_history(self):
        client = self.client()
        with self.assertRaises(ValueError):
            publish_rows(client, [])
        self.assertFalse(any(call.args[0].startswith("EXCHANGE") for call in client.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
