from datetime import date
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from bitrix24.api.deal_views import Updating, bundle
from bitrix24.services.crm_marts import SnapshotChanged


class PublishedDealRefreshTests(SimpleTestCase):
    def setUp(self):
        self.filters = {"date_start": date(2026, 1, 1), "date_end": date(2026, 9, 1), "group_by": "month"}
        self.mart = Mock(snapshot="published", refs={})
        self.mart.deals.return_value = [{"deal_id": 1}]
        self.cache = {}
        self.addCleanup(patch.stopall)
        patch("bitrix24.api.deal_views.reader", return_value=self.mart).start()
        patch("bitrix24.api.deal_views.get_dashboard_cache", side_effect=lambda key: self.cache.get(key["snapshot"])).start()
        self.save = patch("bitrix24.api.deal_views.set_dashboard_cache", side_effect=lambda key, value: self.cache.update({key["snapshot"]: value})).start()
        patch("bitrix24.services.refresh.refresh_state", return_value={"running": True}).start()
        patch("bitrix24.api.deal_views.refresh_state", create=True, return_value={"running": True}).start()

    def test_uncached_report_reads_published_snapshot_during_refresh(self):
        result = bundle("deals", self.filters)
        self.assertEqual(result["current"], [{"deal_id": 1}])
        self.assertEqual(result["snapshot"], "published")
        self.assertEqual(self.mart.deals.call_count, 3)
        self.mart.check.assert_called_once_with()
        self.save.assert_called_once()

    def test_changed_snapshot_is_rejected_and_not_cached(self):
        self.mart.check.side_effect = SnapshotChanged("publication switched")
        with self.assertRaises(Updating):
            bundle("deals", self.filters)
        self.save.assert_not_called()

    def test_new_publication_does_not_reuse_previous_cached_report(self):
        bundle("deals", self.filters)
        self.mart.snapshot = "new-publication"
        self.mart.deals.return_value = [{"deal_id": 2}]
        result = bundle("deals", self.filters)
        self.assertEqual(result["snapshot"], "new-publication")
        self.assertEqual(result["current"], [{"deal_id": 2}])
        self.assertEqual(self.save.call_count, 2)
