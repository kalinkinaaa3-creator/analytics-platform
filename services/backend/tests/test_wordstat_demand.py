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

    def test_previous_period_uses_adjacent_months_across_year_boundary(self):
        for length in (1, 3, 6, 12):
            end = date(2026, 2, 1)
            report = build_demand(dict(end_month=end, period_months=length, comparison="previous_period"), TODAY, source())
            self.assertEqual(report["period"]["previous_start"], shift(end, 1 - 2 * length).isoformat())
            self.assertEqual(report["period"]["comparison"], "previous_period")
            self.assertEqual(report["summary"]["previous_volume"], length * 1000)
        self.assertEqual(report["period"]["previous_end"], "2025-02-28")

    def test_comparison_modes_change_values_but_not_seasonality(self):
        refs, facts, snap = source()
        facts["a"][date(2026, 7, 1)] = 300
        data = refs, facts, snap
        yoy = build_demand(dict(period_months=1), TODAY, data)
        adjacent = build_demand(dict(period_months=1, comparison="previous_period"), TODAY, data)
        self.assertEqual(yoy["summary"]["previous_volume"], 1000)
        self.assertEqual(adjacent["summary"]["previous_volume"], 1200)
        self.assertEqual(yoy["seasonality"], adjacent["seasonality"])
        self.assertEqual(adjacent["period"]["previous_end"], "2026-07-31")

    def test_twelve_month_comparison_modes_are_identical(self):
        a = build_demand(dict(period_months=12), TODAY, source())
        b = build_demand(dict(period_months=12, comparison="previous_period"), TODAY, source())
        self.assertEqual(a["summary"], b["summary"])
        self.assertEqual(a["period"]["previous_start"], b["period"]["previous_start"])

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

    def test_focus_changes_entire_report(self):
        r = build_demand(dict(level="phrase", phrase="a", period_months=1), TODAY, source())
        self.assertEqual(r["summary"]["current_volume"], 100)
        self.assertEqual(r["summary"]["count"], 1)
        self.assertEqual(len(r["items"]), 1)
        self.assertEqual(len(r["seasonality"]), 1)

    def test_multiple_queries_filter_all_totals_and_keep_filter_options(self):
        data = source([("a", "A", "AA", 100), ("b", "A", "AA", 200), ("c", "A", "AA", 900)])
        report = build_demand(dict(level="phrase", element_ids=["A\x1fAA\x1fa", "A\x1fAA\x1fb"], period_months=1), TODAY, data)
        self.assertEqual(report["summary"]["current_volume"], 300)
        self.assertEqual(report["summary"]["count"], 2)
        self.assertEqual({p["phrase"] for p in report["items"]}, {"a", "b"})
        self.assertEqual(len(report["seasonality"]), 2)
        self.assertEqual(len(report["element_options"]), 3)

    def test_multi_category_navigation_and_same_names_do_not_mix_scopes(self):
        data = source([("a", "A", "same", 100), ("b", "B", "same", 200), ("c", "C", "other", 900)])
        report = build_demand(dict(level="phrase", scope_ids=["A\x1fsame", "B\x1fsame"], period_months=1), TODAY, data)
        self.assertEqual(report["summary"]["current_volume"], 300)
        self.assertEqual({p["phrase"] for p in report["element_options"]}, {"a", "b"})

    def test_card_query_selection_recalculates_the_whole_report(self):
        refs, facts, snap = source()
        facts["a"][date(2026, 8, 1)] = 200
        data = refs, facts, snap
        report = build_demand(dict(period_months=1), TODAY, data)
        self.assertEqual(report["summary"]["distribution"]["growth"]["count"], 1)
        ids = [q["id"] for q in report["query_items"] if q["status"] == "growth"]
        narrowed = build_demand(dict(level="phrase", element_ids=ids, period_months=1), TODAY, data)
        self.assertEqual(narrowed["summary"]["current_volume"], 200)
        self.assertEqual(narrowed["summary"]["distribution"]["growth"]["share"], 100)

    def test_latest_loaded_month_remains_available_when_another_query_is_missing(self):
        refs, facts, snap = source()
        facts["b"][date(2026, 8, 1)] = None
        report = build_demand({}, TODAY, (refs, facts, snap))
        self.assertEqual(report["period"]["end_month"], "2026-08")
        self.assertEqual(report["available_months"][-1], "2026-08")
        self.assertEqual(report["month_coverage"]["2026-08"], "partial")
        self.assertIsNone(report["summary"]["current_volume"])

    def test_region_gaps_do_not_invalidate_complete_devices(self):
        day, old = date(2025, 6, 1), date(2024, 6, 1)
        names = [("phone", "phone"), ("desktop", "desktop"), ("tablet", "tablet")]
        values = {("focus", "device", d, m): v for d, v in (("phone", 60), ("desktop", 30), ("tablet", 10)) for m in (day, old)}
        devices = describe_slices(values, "device", names, metrics(100, 100), metrics(None, None), [day], [old], 10)
        regions = describe_slices(values, "region", [("group", "group")], metrics(100, 100), metrics(None, None), [day], [old], 10)
        self.assertTrue(devices["complete"])
        self.assertTrue(devices["consistent"])
        self.assertFalse(regions["complete"])

    def test_seasonality_uses_selected_year_including_current(self):
        a = build_demand(dict(period_months=1), TODAY, source())
        b = build_demand(dict(period_months=12), TODAY, source())
        self.assertEqual(a["seasonality"], b["seasonality"])
        self.assertEqual(a["seasonality"][0]["years"], [2026])
        self.assertEqual(a["seasonality"][0]["coefficients"], [1] * 8 + [None] * 4)
        old = build_demand(dict(end_month=date(2025, 6, 1)), TODAY, source())
        self.assertEqual(old["seasonality"][0]["coefficients"], [1] * 12)

    def test_seasonality_matches_average_of_rounded_query_coefficients(self):
        refs, facts, snap = source()
        facts["a"] = {date(2026, 1, 1): 10, date(2026, 2, 1): 30}
        facts["b"] = {date(2026, 1, 1): 900, date(2026, 2, 1): 900}
        result = build_demand(dict(end_month=date(2026, 2, 1)), TODAY, (refs, facts, snap))
        self.assertEqual(result["seasonality"][0]["coefficients"][:2], [.75, 1.25])

    def test_zero_seasonality_and_missing_month_are_different(self):
        monthly = {date(2026, 1, 1): 0, date(2026, 2, 1): 0}
        self.assertEqual(season_profile(monthly, TODAY)["coefficients"][:3], [0, 0, None])

    def test_current_year_positive_and_negative_changes_are_numeric(self):
        refs, facts, snap = source()
        facts["a"][date(2026, 8, 1)] = 200
        facts["b"][date(2026, 8, 1)] = 450
        result = build_demand(dict(level="phrase", period_months=1), TODAY, (refs, facts, snap))
        growth = {i["phrase"]: i["growth_percent"] for i in result["items"]}
        self.assertEqual(growth, {"a": 100, "b": -50})

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

    def test_overlapping_slices_remain_visible(self):
        day = date(2026, 8, 1)
        result = describe_slices({("focus", "device", "phone", day): 101}, "device", [("phone", "Phone")], metrics(100, 100), metrics(None, None), [day], [date(2025, 8, 1)], 10)
        self.assertTrue(result["consistent"])
        self.assertEqual(result["leader"]["share"], 101)
        self.assertEqual(result["other_share"], 0)
        self.assertIsNone(result["reason"])

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
    def test_statistics_staging_failure_preserves_published_table(self):
        import importlib.util
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        path = Path(__file__).parents[1] / "analytics/services/yd_wordstat_sync.py"
        for fail in (False, True):
            client = Mock()
            def execute(sql, rows=None):
                if sql.startswith("SELECT engine"):
                    return [("Atomic",)]
                if sql.startswith("INSERT") and fail:
                    raise RuntimeError("staging failed")
                if sql.startswith("SELECT count"):
                    return [(1,)]
            client.execute.side_effect = execute
            with patch.dict(sys.modules, {
                "analytics.clickhouse.repository": SimpleNamespace(YD_WORDSTAT_COLUMNS=["phrase", "year", "month_1"]),
                "analytics.clickhouse.client": SimpleNamespace(get_clickhouse_client=lambda: client),
                "analytics.clickhouse.schema": SimpleNamespace(ensure_yd_wordstat_for_table=Mock()),
            }):
                spec = importlib.util.spec_from_file_location("wordstat_sync_test", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with patch.object(module, "YdWordstatFor") as model:
                    model.objects.all.return_value.order_by.return_value.values.return_value = [
                        dict(phrase="a", year=2026, month_1=100)]
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, "staging failed"):
                            module.sync_yd_wordstat_to_clickhouse()
                    else:
                        self.assertEqual(module.sync_yd_wordstat_to_clickhouse(), 1)
            sql = [c.args[0] for c in client.execute.call_args_list]
            self.assertEqual(any(q.startswith("EXCHANGE") for q in sql), not fail)
            self.assertFalse(any("TRUNCATE" in q for q in sql))
            client.disconnect.assert_called_once()

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
