import unittest
from datetime import date
from unittest.mock import patch

from analytics.services.fb_turnover_prepare import build_turnover_chart_data


class TurnoverChartTests(unittest.TestCase):
    def chart(self, rows, plan_date, start, end, today=date(2026, 9, 8)):
        with patch("analytics.services.fb_turnover_prepare.date") as clock:
            clock.today.return_value = today
            # date_to_str uses isinstance(value, date).
            clock.side_effect = date
            with patch("analytics.services.fb_turnover_prepare.date_to_str", side_effect=lambda d: d.isoformat()):
                return build_turnover_chart_data(rows, [{"date_start": plan_date, "indicator": 100}], start, end)

    def test_past_month_plan_and_fact_share_month_end(self):
        result = self.chart([{"date_end": date(2026, 8, 31), "middle_rubstock": 80}],
                            date(2026, 8, 1), "2026-08-01", "2026-08-31")
        self.assertEqual([p["label"] for p in result["x_labels"]], ["2026-08-31"])
        self.assertEqual([p["value"] for p in result["final_stock"]], [80])
        self.assertEqual([p["value"] for p in result["mutual_finstock"]], [100])
        self.assertEqual(result["final_stock"][0]["x"], result["mutual_finstock"][0]["x"])

    def test_plan_only_past_month_uses_leap_year_end(self):
        result = self.chart([], date(2024, 2, 1), "2024-02-01", "2024-02-29")
        self.assertEqual([p["label"] for p in result["x_labels"]], ["2024-02-29"])
        self.assertEqual(result["final_stock"], [])

    def test_month_end_outside_selected_range_is_not_added(self):
        self.assertIsNone(self.chart([], date(2026, 8, 1), "2026-08-01", "2026-08-15"))

    def test_current_month_keeps_daily_points(self):
        result = self.chart([{"date_end": date(2026, 9, 7), "middle_rubstock": 80}],
                            date(2026, 9, 1), "2026-09-01", "2026-09-07")
        self.assertEqual([p["label"] for p in result["x_labels"]], ["2026-09-01", "2026-09-07"])

    def test_monthly_scale_keeps_one_month_label(self):
        result = self.chart([{"date_end": date(2026, 8, 31), "middle_rubstock": 80}],
                            date(2026, 8, 1), "2026-01-01", "2026-08-31")
        self.assertEqual([p["label"] for p in result["x_labels"]], ["2026-08"])
