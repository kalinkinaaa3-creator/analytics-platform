"""Isolated quota tests: real in-memory state, fake clock and HTTP responses."""
from contextlib import ExitStack
from datetime import date, datetime, timezone
from email.utils import format_datetime
from unittest import TestCase, SkipTest
from unittest.mock import Mock, patch

from django.db import connection
from django.test import override_settings

from datasets.models import YdWordstatApiQuota
from datasets.services.external_api import yd_wordstat_search_api_client as client


class WordstatQuotaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "sqlite" or connection.settings_dict["NAME"] != ":memory:":
            raise SkipTest("Requires a dedicated in-memory SQLite database")
        cls.created_table = YdWordstatApiQuota._meta.db_table not in connection.introspection.table_names()
        if cls.created_table:
            with connection.schema_editor() as editor:
                editor.create_model(YdWordstatApiQuota)

    @classmethod
    def tearDownClass(cls):
        if cls.created_table:
            with connection.schema_editor() as editor:
                editor.delete_model(YdWordstatApiQuota)
        super().tearDownClass()

    def setUp(self):
        YdWordstatApiQuota.objects.all().delete()
        self.clock = 10000.
        self.pauses = []
        stack = self.enterContext(ExitStack())
        stack.enter_context(override_settings(
            YD_WORDSTAT_API_KEY="test-key", YD_WORDSTAT_FOLDER_ID="test-folder",
            YD_WORDSTAT_API_BASE_URL="https://searchapi.api.cloud.yandex.net/v2/wordstat",
            YD_WORDSTAT_REQUESTS_PER_SECOND=20, YD_WORDSTAT_REQUESTS_PER_HOUR=100,
            YD_WORDSTAT_API_MAX_ATTEMPTS=2, YD_WORDSTAT_API_CONNECT_TIMEOUT=1,
            YD_WORDSTAT_API_TIMEOUT=1,
        ))
        stack.enter_context(patch.object(client.time, "time", side_effect=lambda: self.clock))
        stack.enter_context(patch.object(client.time, "sleep", side_effect=self.sleep))
        stack.enter_context(patch.object(client.logger, "info"))
        stack.enter_context(patch.object(client.logger, "warning"))
        self.post = stack.enter_context(patch.object(client.requests, "post"))

    def sleep(self, seconds):
        self.pauses.append(seconds)
        self.clock += seconds

    @staticmethod
    def response(status=200, headers=None, data=None):
        return Mock(status_code=status, headers=headers or {}, json=Mock(return_value=data or {"regions": [{"id": 1}]}))

    def test_tree_waits_remaining_saved_block_before_any_http_request(self):
        YdWordstatApiQuota.objects.create(scope=client.quota_scope(), blocked_until=self.clock + 125)
        requested_at = []
        self.post.side_effect = lambda *args, **kwargs: requested_at.append(self.clock) or self.response()
        client.fetch_regions_tree()
        self.assertEqual(self.post.call_count, 1)
        self.assertGreaterEqual(requested_at[0], 10125)
        self.assertLess(requested_at[0], 10126)
        self.assertLessEqual(max(self.pauses), 60)

    def test_tree_respects_saved_rolling_hour_budget(self):
        with override_settings(YD_WORDSTAT_REQUESTS_PER_HOUR=1):
            YdWordstatApiQuota.objects.create(scope=client.quota_scope(), requests=[self.clock - 3500])
            self.post.return_value = self.response()
            client.fetch_regions_tree()
        self.assertAlmostEqual(sum(self.pauses), 100.05)
        state = YdWordstatApiQuota.objects.get(scope=client.quota_scope())
        self.assertEqual(len(state.requests), 1)
        self.assertGreaterEqual(state.requests[0], 10100)

    def test_tree_429_retry_after_is_persisted_and_honored(self):
        self.post.side_effect = [self.response(429, {"Retry-After": "120"}), self.response()]
        client.fetch_regions_tree()
        state = YdWordstatApiQuota.objects.get(scope=client.quota_scope())
        self.assertEqual(state.blocked_until, 10120)
        self.assertGreaterEqual(state.requests[1] - state.requests[0], 120)
        self.assertEqual(self.post.call_count, 2)

    def test_final_429_survives_restart_without_resetting_hour_wait(self):
        with override_settings(YD_WORDSTAT_API_MAX_ATTEMPTS=1):
            self.post.return_value = self.response(429)
            with self.assertRaises(client.YdWordstatSearchApiError):
                client.fetch_regions_tree()
        self.assertEqual(YdWordstatApiQuota.objects.get().blocked_until, 13600)
        self.assertEqual(self.pauses, [])
        # A later invocation re-reads the DB, just as a restarted process does.
        self.clock += 900
        self.post.return_value = self.response()
        client.fetch_regions_tree()
        self.assertGreaterEqual(sum(self.pauses), 2700)
        self.assertLess(sum(self.pauses), 2701)
        self.assertEqual(YdWordstatApiQuota.objects.get().blocked_until, 13600)

    def test_stopping_during_wait_keeps_persisted_state(self):
        YdWordstatApiQuota.objects.create(scope=client.quota_scope(), blocked_until=10120)
        with patch.object(client.time, "sleep", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            client.fetch_regions_tree()
        self.post.assert_not_called()
        self.clock += 90
        self.post.return_value = self.response()
        client.fetch_regions_tree()
        self.assertAlmostEqual(sum(self.pauses), 30.05)

    def test_dynamics_uses_same_block_as_tree(self):
        with override_settings(YD_WORDSTAT_API_MAX_ATTEMPTS=1):
            self.post.return_value = self.response(429, {"Retry-After": "75"})
            with self.assertRaises(client.YdWordstatSearchApiError):
                client.fetch_regions_tree()
        self.post.return_value = self.response(data={"data": []})
        client.fetch_dynamics("test", date(2025, 1, 1), date(2025, 1, 31))
        self.assertAlmostEqual(sum(self.pauses), 75.05)
        self.assertEqual(YdWordstatApiQuota.objects.count(), 1)

    def test_folder_override_uses_its_own_persistent_scope(self):
        YdWordstatApiQuota.objects.create(scope=client.quota_scope("another-folder"), blocked_until=10030)
        self.post.return_value = self.response()
        client.fetch_regions_tree(folder_id="another-folder")
        self.assertAlmostEqual(sum(self.pauses), 30.05)
        self.assertEqual(self.post.call_args.kwargs["json"]["folderId"], "another-folder")
        self.assertFalse(YdWordstatApiQuota.objects.filter(scope=client.quota_scope()).exists())

    def test_retry_after_http_date_invalid_and_nonfinite_values(self):
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        with patch.object(client, "datetime") as clock:
            clock.now.return_value = now
            value = format_datetime(datetime(2026, 10, 6, 0, 2, tzinfo=timezone.utc), usegmt=True)
            self.assertEqual(client.retry_after(self.response(429, {"Retry-After": value}), 3600), 120)
        for value in ("", "invalid", "inf", "NaN"):
            self.assertEqual(client.retry_after(self.response(429, {"Retry-After": value}), 3600), 3600)

    def test_nonretryable_http_error_does_not_create_block(self):
        self.post.return_value = self.response(403)
        with self.assertRaises(client.YdWordstatSearchApiError):
            client.fetch_regions_tree()
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(YdWordstatApiQuota.objects.get().blocked_until, 0)

    def test_new_short_block_does_not_shorten_existing_block(self):
        client.block_quota(120)
        client.block_quota(10)
        self.assertEqual(YdWordstatApiQuota.objects.get().blocked_until, 10120)
