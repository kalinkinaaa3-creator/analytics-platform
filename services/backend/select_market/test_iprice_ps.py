from unittest.mock import patch
from django.test import TestCase, override_settings
from datasets.models import ParserProductUrl as LegacyUrl, PsProductPrice as LegacyPrice
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers import ps_links, ps_product_parser as parser, global_queue
from datasets.services.parsers.global_queue import QueueOwnershipError
from organizations.models import Organization
from .iprice_domain_models import ParserPrefix, ParserProductUrl, PsProductPrice
from .iprice_competitors import collect_competitor
from .test_iprice_tt import InlineExecutor


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True, TARA_PARSER_WORKERS=1)
class PSTests(TestCase):
    def setUp(self):
        self.sm = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")
        self.iplast = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        self.workspace = IPriceWorkspace("select-market")
        self.local = ParserProductUrl.objects.create(source="ps", url="https://plastic-system.ru/local", status="active")
        self.legacy = LegacyUrl.objects.create(id=self.local.pk, source="ps", url="https://plastic-system.ru/legacy", status="active")
        ParserPrefix.objects.create(source="ps", prefix="spb")

    def test_storage_and_errors_are_local_and_legacy_default_remains(self):
        parser.save_product_data(self.local, {"price": 122, "final_price": 100}, [], workspace=self.workspace)
        self.assertEqual(PsProductPrice.objects.get().final_price, 100)
        self.assertFalse(LegacyPrice.objects.exists())
        parser.save_product_data(self.legacy, {"price": 244, "final_price": 200}, [])
        self.assertEqual(LegacyPrice.objects.get().final_price, 200)
        parser.mark_url_not_found(self.local.pk, RuntimeError("missing"), workspace=self.workspace)
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, "active")

    def test_worker_uses_local_url(self):
        with patch.object(parser, "ThreadPoolExecutor", InlineExecutor), patch.object(parser, "fetch_html", side_effect=parser.PsNotFoundError("missing")) as fetch:
            result = parser.parse_ps_products(workspace=self.workspace, workers=1)
        self.assertEqual(result["not_found"], 1)
        fetch.assert_called_once_with(self.local.url)
        self.legacy.refresh_from_db()
        self.assertIsNone(self.legacy.last_error)

    def test_partial_catalog_rolls_back(self):
        categories = [{"url": "a", "category": "A"}, {"url": "b", "category": "B"}]
        with patch.object(ps_links, "extract_category_urls", return_value=categories), patch.object(ps_links, "extract_product_urls_from_category", side_effect=[["https://plastic-system.ru/new"], RuntimeError("network")]), self.assertRaises(RuntimeError):
            ps_links.sync_ps_product_urls(workspace=self.workspace)
        self.assertEqual(ParserProductUrl.objects.count(), 1)
        self.local.refresh_from_db()
        self.assertEqual(self.local.status, "active")

    def test_page_error_propagates_in_strict_mode(self):
        with patch.object(ps_links, "fetch_html", side_effect=RuntimeError("network")), self.assertRaises(RuntimeError):
            ps_links.extract_product_urls_from_category("https://example.test/category", "https://example.test", strict=True)

    def test_empty_region_keeps_existing_links(self):
        with patch.object(ps_links, "extract_category_urls", return_value=[]), self.assertRaises(RuntimeError):
            ps_links.sync_ps_product_urls(workspace=self.workspace)
        self.local.refresh_from_db()
        self.assertEqual(self.local.status, "active")

    def test_busy_slot_prevents_network(self):
        global_queue.enqueue(organization=self.iplast, kind="master", run_id=1)
        global_queue.claim_next(executor="other")
        with patch.object(ps_links, "extract_category_urls") as fetch, self.assertRaises(QueueOwnershipError):
            collect_competitor("ps", workspace=self.workspace, sync_links=True)
        fetch.assert_not_called()

    def test_links_use_only_local_storage(self):
        with patch.object(ps_links, "extract_category_urls", return_value=[{"url": "a", "category": "A"}]), patch.object(ps_links, "extract_product_urls_from_category", return_value=["https://plastic-system.ru/new"]) as pages:
            result = ps_links.sync_ps_product_urls(workspace=self.workspace)
        self.assertTrue(pages.call_args.kwargs["strict"])
        self.assertEqual(result["created"], 1)
        self.assertEqual(LegacyUrl.objects.count(), 1)
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, "active")
