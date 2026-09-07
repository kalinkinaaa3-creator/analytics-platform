"""Offline notification checks. HTTP, models and workers are mocked."""
import ast
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ["DJANGO_SETTINGS_MODULE"] = "tests.wordstat_settings"
import django
django.setup()
from django.test import SimpleTestCase, override_settings
from analytics.services import bitrix_notify


def isolated_function(relative_path, name, namespace):
    """Load only the tested function, without app startup or background workers."""
    path = Path(__file__).parents[1] / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


@override_settings(ENABLE_BITRIX_NOTIFICATIONS=True, BITRIX_WEBHOOK_URL="https://example.invalid/webhook", BITRIX_NOTIFY_USER_ID="test")
class BitrixNotificationTests(SimpleTestCase):
    def test_success_and_api_error_in_http_200_are_distinguished(self):
        for payload, expected in (({"result": 123}, True), ({"error": "ERROR_METHOD_NOT_FOUND"}, False)):
            response = Mock()
            response.json.return_value = payload
            with patch.object(bitrix_notify.requests, "post", return_value=response) as post:
                self.assertEqual(bitrix_notify.send_bitrix_message("test"), expected)
                post.assert_called_once()

    @override_settings(ENABLE_BITRIX_NOTIFICATIONS=False)
    def test_disabled_notifications_do_not_send(self):
        with patch.object(bitrix_notify.requests, "post") as post:
            self.assertFalse(bitrix_notify.send_bitrix_message("test"))
            post.assert_not_called()

    def test_network_failure_does_not_raise(self):
        with patch.object(bitrix_notify.requests, "post", side_effect=RuntimeError("offline")):
            self.assertFalse(bitrix_notify.send_bitrix_message("test"))


class LoaderNotificationTests(unittest.TestCase):
    def test_api_failures_notify_once_and_preserve_original_exception(self):
        cases = [
            ("datasets/services/external_api/nomenclature_api_loader.py", "load_nomenclature_from_api", "fetch_nomenclature_api_rows"),
            ("datasets/services/external_api/price_api_loader.py", "load_prices_from_api", "get_price_load_period"),
            ("analytics/services/planned_sales_csv_pipeline.py", "run_planned_sales_csv_pipeline", "load_dash_sales_from_csv"),
        ]
        for path, name, dependency in cases:
            failure = RuntimeError("source unavailable")
            send = Mock(return_value=False)
            fn = isolated_function(path, name, {"logger": Mock(), "send_bitrix_message": send,
                "date": date, dependency: Mock(side_effect=failure)})
            with self.assertRaises(RuntimeError) as caught:
                fn("file.csv") if name.endswith("csv_pipeline") else fn()
            self.assertIs(caught.exception, failure)
            send.assert_called_once()

    def test_seo_failure_notifies_once_per_run(self):
        send = Mock()
        fn = isolated_function("seo_analytics/services/refresh.py", "fail_run", {
            "SeoRefreshRun": SimpleNamespace(Status=SimpleNamespace(FAILED="failed")),
            "timezone": Mock(), "cache": Mock(), "LOCK_KEY": "lock", "logger": Mock(),
            "_notify_refresh": Mock(), "send_bitrix_message": send})
        run = Mock(status="running", id=7)
        fn(run, RuntimeError("failure"))
        fn(run, RuntimeError("same failure"))
        self.assertEqual(run.status, "failed")
        send.assert_called_once()

    def test_context_success_is_silent_and_failure_notifies_once(self):
        send = Mock()
        fn = isolated_function("context_analytics/services/refresh.py", "finish", {
            "timezone": Mock(), "cache": Mock(), "LOCK_KEY": "lock", "logger": Mock(),
            "_notify": Mock(), "send_bitrix_message": send})
        fn(Mock(status="running"), stats={"rows": 10})
        send.assert_not_called()
        run = Mock(status="running", id=8)
        fn(run, error=RuntimeError("failure"))
        fn(run, error=RuntimeError("same failure"))
        send.assert_called_once()

    def test_crm_failure_marks_exception_to_prevent_pipeline_duplicate(self):
        transaction = Mock()
        transaction.on_commit.side_effect = lambda callback: callback()
        fn = isolated_function("bitrix24/services/sync_state.py", "fail_sync", {
            "BitrixSyncRun": SimpleNamespace(Status=SimpleNamespace(FAILED="failed")),
            "BitrixSyncState": Mock(), "transaction": transaction, "timezone": Mock()})
        failure = RuntimeError("failure")
        with patch.object(bitrix_notify, "send_bitrix_message") as send:
            fn(Mock(entity="leads", pk=9), failure)
            fn(Mock(entity="leads", pk=9), failure)
            send.assert_called_once()
            self.assertTrue(failure._bitrix_notification_attempted)
