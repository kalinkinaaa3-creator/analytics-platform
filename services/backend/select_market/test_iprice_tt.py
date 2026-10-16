from concurrent.futures import Future
from unittest.mock import patch

from django.test import TestCase, override_settings
from datasets.models import ParserProductUrl as LegacyUrl, TtProductPrice as LegacyPrice
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers import tt_links, tt_product_parser as parser
from datasets.services.parsers import global_queue
from datasets.services.parsers.global_queue import QueueOwnershipError
from datasets.management.commands.load_select_market_tt import load_tt
from datasets.parser_queue_models import ParserQueueEntry
from organizations.models import Organization
from .iprice_domain_models import ParserProductUrl, TtProductPrice


class InlineExecutor:
    """Keep SQLite writes on the test transaction; exercise submitted arguments."""
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True, TARA_PARSER_WORKERS=1)
class TTTests(TestCase):
    def setUp(self):
        self.sm = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")
        self.iplast = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        self.workspace = IPriceWorkspace("select-market")
        self.local = ParserProductUrl.objects.create(source="tt", url="https://toptara.ru/local", status="active")
        self.legacy = LegacyUrl.objects.create(id=self.local.pk, source="tt", url="https://toptara.ru/legacy", status="active")

    def test_product_storage_and_errors_are_local(self):
        parser.save_product_data(self.local, [{"price": 122, "final_price": 100}], [{"properties": "Color", "value": "Green"}], {"name": "Box"}, workspace=self.workspace)
        self.assertEqual(TtProductPrice.objects.get().final_price, 100)
        self.assertFalse(LegacyPrice.objects.exists())
        parser.mark_url_not_found(self.local.pk, RuntimeError("missing"), workspace=self.workspace)
        self.local.refresh_from_db()
        self.legacy.refresh_from_db()
        self.assertEqual(self.local.status, "inactive")
        self.assertEqual(self.legacy.status, "active")
        self.assertIsNone(self.legacy.last_error)

    def test_worker_receives_workspace_and_does_not_touch_legacy(self):
        with patch.object(parser, "ThreadPoolExecutor", InlineExecutor), patch.object(parser, "fetch_html", side_effect=parser.TtNotFoundError("missing")) as fetch:
            result = parser.parse_tt_products(workspace=self.workspace, workers=1)
        self.assertEqual(result["not_found"], 1)
        fetch.assert_called_once_with(self.local.url)
        self.legacy.refresh_from_db()
        self.assertIsNone(self.legacy.last_error)

    def test_empty_catalog_rolls_back_without_deactivating_links(self):
        with patch.object(tt_links, "extract_category_urls", return_value=[]), self.assertRaises(RuntimeError):
            tt_links.sync_tt_product_urls(workspace=self.workspace)
        self.local.refresh_from_db()
        self.assertEqual(self.local.status, "active")

    def test_link_sync_writes_only_local_catalog(self):
        with patch.object(tt_links, "extract_category_urls", return_value=[{"url": "category", "category": "Boxes"}]), patch.object(tt_links, "extract_product_urls_from_category", return_value=["https://toptara.ru/new"]), patch.object(tt_links, "fetch_html", return_value="<html></html>"):
            result = tt_links.sync_tt_product_urls(workspace=self.workspace)
        self.assertEqual(result["created"], 1)
        self.assertTrue(ParserProductUrl.objects.filter(url="https://toptara.ru/new").exists())
        self.assertEqual(LegacyUrl.objects.count(), 1)
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, "active")

    def test_busy_slot_prevents_network(self):
        global_queue.enqueue(organization=self.iplast, kind="master", run_id=1)
        global_queue.claim_next(executor="other")
        with patch.object(tt_links, "extract_category_urls") as fetch, self.assertRaises(QueueOwnershipError):
            load_tt(workspace=self.workspace, sync_links=True)
        fetch.assert_not_called()

    def test_nested_steps_share_one_slot(self):
        with patch.object(parser, "ThreadPoolExecutor", InlineExecutor), patch.object(parser, "parse_one_url", return_value={"product_url_id": self.local.pk, "product_key": self.local.pk, "properties": 0, "prices": 0}):
            result = load_tt(workspace=self.workspace)
        self.assertEqual(result["products"]["success"], 1)
        self.assertEqual(ParserQueueEntry.objects.count(), 1)
        self.assertEqual(ParserQueueEntry.objects.get().status, "success")

    def test_legacy_default_storage_is_preserved(self):
        parser.save_product_data(self.legacy, [{"price": 122, "final_price": 100}], [], {"name": "Legacy"})
        self.assertEqual(LegacyPrice.objects.get().final_price, 100)
        self.assertFalse(TtProductPrice.objects.exists())

    def test_partial_link_failure_rolls_back_new_links(self):
        with patch.object(tt_links, "extract_category_urls", return_value=[{"url": "category", "category": "Boxes"}]), patch.object(tt_links, "extract_product_urls_from_category", return_value=["https://toptara.ru/new", "https://toptara.ru/broken"]), patch.object(tt_links, "fetch_html", side_effect=["<html></html>", RuntimeError("network")]), self.assertRaises(RuntimeError):
            tt_links.sync_tt_product_urls(workspace=self.workspace)
        self.assertEqual(ParserProductUrl.objects.count(), 1)
        self.local.refresh_from_db()
        self.assertEqual(self.local.status, "active")

    def test_failed_collection_is_not_reported_as_success(self):
        with patch.object(parser, "ThreadPoolExecutor", InlineExecutor), patch.object(parser, "fetch_html", side_effect=RuntimeError("network")), self.assertRaises(RuntimeError):
            load_tt(workspace=self.workspace)
        self.assertEqual(ParserQueueEntry.objects.get().status, "failed")
        self.assertFalse(ParserQueueEntry.objects.filter(status__in=ParserQueueEntry.OCCUPIED).exists())
