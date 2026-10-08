from datetime import date, timedelta
from unittest import TestCase

from bitrix24.services.reconciliation_periods import reconciliation_windows


class ReconciliationPeriodTests(TestCase):
    def test_sunday_keeps_leads_14_days_and_deals_four_calendar_months(self):
        leads, deals, end = reconciliation_windows(date(2026, 10, 11))
        self.assertEqual(leads.isoformat(), "2026-09-27T00:00:00+03:00")
        self.assertEqual(deals.isoformat(), "2026-06-11T00:00:00+03:00")
        self.assertEqual(end.isoformat(), "2026-10-11T00:00:00+03:00")
        self.assertEqual(end - leads, timedelta(days=14))

    def test_month_end_is_clamped_to_last_existing_day(self):
        for boundary, expected in [(date(2026, 8, 31), date(2026, 4, 30)),
                                   (date(2026, 6, 30), date(2026, 2, 28)),
                                   (date(2024, 6, 30), date(2024, 2, 29)),
                                   (date(2026, 1, 11), date(2025, 9, 11))]:
            with self.subTest(boundary=boundary):
                _, deals, _ = reconciliation_windows(boundary)
                self.assertEqual(deals.date(), expected)

    def test_windows_can_be_configured_independently(self):
        leads, deals, end = reconciliation_windows(date(2026, 10, 11), lead_days=7, deal_months=2)
        self.assertEqual(end - leads, timedelta(days=7))
        self.assertEqual(deals.date(), date(2026, 8, 11))

    def test_invalid_periods_are_rejected_before_loading(self):
        for kwargs in ({"lead_days": 0}, {"deal_months": 0}, {"deal_months": -1}, {"deal_months": 100000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reconciliation_windows(date(2026, 10, 11), **kwargs)
