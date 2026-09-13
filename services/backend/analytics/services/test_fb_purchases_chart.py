from datetime import date
from unittest import TestCase

from .fb_purchases_prepare import build_price_chart_data


class PurchasesChartScaleTests(TestCase):
    def test_axis_is_bounded_and_preserves_prices(self):
        for fact, plan in [(100, 96), (28514.44, 96), (1000000000, 96),
                           (96, 96), (0, 0), (-28514.44, 96), (0.01, 0.02)]:
            with self.subTest(fact=fact, plan=plan):
                chart = build_price_chart_data(
                    [{"date_draft": date(2026, 9, 7), "quantity_1C": 1,
                      "revenue_1C": fact, "VAT_1C": 0}],
                    [{"date_draft": date(2026, 9, 1), "indicator": plan}],
                )
                axis = chart["y_axis"]
                self.assertLessEqual(len(axis["ticks"]), 8)
                self.assertLess(axis["min"], min(fact, plan))
                self.assertGreater(axis["max"], max(fact, plan))
                self.assertEqual(chart["fact"][0]["value"], fact)
                for point in chart["fact"] + chart["plan"]:
                    self.assertTrue(0 <= point["y"] <= 1)

    def test_small_range_keeps_original_five_ruble_step(self):
        chart = build_price_chart_data(
            [{"date_draft": date(2026, 9, 7), "quantity_1C": 1, "revenue_1C": 100}],
            [{"date_draft": date(2026, 9, 1), "indicator": 96}],
        )
        self.assertEqual([tick["value"] for tick in chart["y_axis"]["ticks"]], [90, 95, 100, 105])
