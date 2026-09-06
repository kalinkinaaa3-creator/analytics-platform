from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from lead_generation.services import _facts, _plan_report, normalize_filters


class LeadGenerationReportTests(SimpleTestCase):
    def test_reverse_period_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Конечная неделя"):
            normalize_filters({"week_from": "2026-02-02", "week_to": "2026-01-12"})

    @patch("lead_generation.services._dict_rows")
    @patch("lead_generation.services.ensure_mart_table")
    def test_select_market_adds_only_additional_apm(self, ensure, dict_rows):
        ensure.return_value = object()
        dict_rows.return_value = [{
            "week_start": date(2026, 1, 12), "direct_cost": 0,
            "total_leads": 20, "target_leads": 5, "additional_apm_leads": 3,
            "non_target_leads": 4, "unprocessed_leads": 2, "opportunity": 0,
        }]
        common = {"week_from": date(2026, 1, 12), "week_to": date(2026, 1, 12)}
        with_apm = _facts({**common, "include_select_market": True})
        without_apm = _facts({**common, "include_select_market": False})
        self.assertEqual(with_apm[date(2026, 1, 12)]["target_leads"], 8)
        self.assertEqual(without_apm[date(2026, 1, 12)]["target_leads"], 5)

    @patch("lead_generation.services._plan_rows")
    @patch("lead_generation.services._facts")
    def test_weekly_derivatives_are_calculated_from_base_values(self, facts, plans):
        week = date(2026, 1, 12)
        facts.return_value = {week: {
            "direct_cost": 600, "total_leads": 20, "target_leads": 5,
            "non_target_leads": 10, "unprocessed_leads": 5, "opportunity": 5000,
        }}
        plans.return_value = {week: SimpleNamespace(
            budget_vat=1000, target_lead_price=150, target_leads=10,
            revenue_plan=5000,
        )}
        row = _plan_report({
            "week_from": week, "week_to": week, "include_select_market": False,
        })[0]
        self.assertEqual(row["actual_target_cpl"], 120)
        self.assertEqual(row["target_conversion"], 25)
        self.assertEqual(row["budget_revenue_share"], 20)
        self.assertEqual(row["target_cpl_delta"], 30)

