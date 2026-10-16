import xml.etree.ElementTree as ET
from unittest.mock import patch

from django.test import TestCase, override_settings
from datasets.models import BaseProductPrice as LegacyPrice, ParserProductUrl as LegacyUrl
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers.base_parser import BaseParserError, load_base_products, parse_offer
from datasets.services.parsers.global_queue import QueueOwnershipError, enqueue, claim_next
from organizations.models import Organization
from .iprice_domain_models import BaseProductPrice, ParserProductUrl, ParserProductProperty


def xml(*codes):
    root = ET.Element("yml_catalog")
    for index, code in enumerate(codes, 1):
        offer = ET.SubElement(root, "offer", id=str(index))
        ET.SubElement(offer, "url").text = f"https://example.test/{code}"
        ET.SubElement(offer, "name").text = "Product"
        ET.SubElement(offer, "price").text = "122"
        ET.SubElement(offer, "param", name="Код товара").text = code
        ET.SubElement(offer, "param", name="Материал").text = "PP"
    return root


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True)
class YmlTests(TestCase):
    def setUp(self):
        self.sm = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")
        self.old = Organization.objects.create(code="iplast", name="Iplast", postgres_schema="public")
        self.workspace = IPriceWorkspace("select-market")

    def load(self, *codes, limit=None):
        with patch("datasets.services.parsers.base_parser.fetch_yml_root", return_value=xml(*codes)):
            return load_base_products(workspace=self.workspace, limit=limit)

    def test_text_codes_isolation_and_source_price_normalization(self):
        LegacyUrl.objects.create(source="base", url="https://legacy.test/item", status="active")
        result = self.load("00-АБ-1")
        row = BaseProductPrice.objects.get()
        self.assertEqual(row.code_1c, "00-АБ-1")
        self.assertEqual(row.final_price, 100)
        self.assertEqual(result["unmatched_sps_codes"], 1)
        self.assertEqual(ParserProductProperty.objects.get().value, "PP")
        self.assertFalse(LegacyPrice.objects.exists())
        self.assertEqual(LegacyUrl.objects.get().status, "active")

    def test_empty_or_invalid_catalog_does_not_deactivate(self):
        self.load("001")
        for root in (xml(), ET.fromstring('<yml_catalog><offer id="1"/></yml_catalog>')):
            with patch("datasets.services.parsers.base_parser.fetch_yml_root", return_value=root), self.assertRaises(BaseParserError):
                load_base_products(workspace=self.workspace)
        self.assertEqual(ParserProductUrl.objects.get().status, "active")

    def test_limit_does_not_deactivate_unprocessed_products(self):
        self.load("001", "002")
        self.load("001", "002", limit=1)
        self.assertEqual(ParserProductUrl.objects.filter(status="active").count(), 2)

    def test_full_catalog_marks_missing_product_inactive(self):
        self.load("001", "002")
        self.load("001")
        self.assertEqual(ParserProductUrl.objects.filter(status="inactive").count(), 1)

    def test_storage_failure_rolls_back_url_sync_and_prices(self):
        self.load("001")
        with patch("datasets.services.parsers.base_parser.save_base_offer_data", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.load("002")
        self.assertEqual(ParserProductUrl.objects.get().url, "https://example.test/001")
        self.assertEqual(BaseProductPrice.objects.get().code_1c, "001")

    def test_busy_other_organization_never_fetches_yml(self):
        enqueue(organization=self.old, kind="master", run_id=1)
        claim_next(executor="legacy")
        with patch("datasets.services.parsers.base_parser.fetch_yml_root") as fetch, self.assertRaises(QueueOwnershipError):
            load_base_products(workspace=self.workspace)
        fetch.assert_not_called()

    @override_settings(PARSER_SHARED_QUEUE_ENABLED=False)
    def test_new_workspace_requires_queue_enabled(self):
        with patch("datasets.services.parsers.base_parser.fetch_yml_root") as fetch, self.assertRaises(QueueOwnershipError):
            load_base_products(workspace=self.workspace)
        fetch.assert_not_called()

    def test_legacy_parser_keeps_numeric_code(self):
        offer = xml("001").find("offer")
        self.assertEqual(parse_offer(offer)["code_1c"], 1)
        self.assertEqual(parse_offer(offer, workspace=self.workspace)["code_1c"], "001")

    @override_settings(SELECT_MARKET_IPRICE_YML_URL="")
    def test_default_feed_is_select_market_and_zero_price_is_not_a_missing_product(self):
        from datasets.services.parsers.base_parser import SELECT_MARKET_YML_URL
        root = xml("8-000000212")
        root.find("offer").set("available", "false")
        root.find("offer/price").text = "0"
        with patch("datasets.services.parsers.base_parser.fetch_yml_root", return_value=root) as fetch:
            load_base_products(workspace=self.workspace)
        fetch.assert_called_once_with(url=SELECT_MARKET_YML_URL)
        self.assertEqual(BaseProductPrice.objects.get().code_1c, "8-000000212")
        self.assertEqual(ParserProductUrl.objects.get().status, "active")

    def test_sps_matching_is_exact_and_does_not_create_products(self):
        from select_market.models import Product, Node
        node = Node.objects.create(code="root", name="Root", level=1)
        Product.objects.create(sku="001", name="Existing", node=node)
        result = self.load("001", "1")
        self.assertEqual(result["matched_sps_codes"], 1)
        self.assertEqual(result["unmatched_sps_codes"], 1)
        self.assertEqual(Product.objects.count(), 1)

    def test_duplicate_url_rejected_before_write(self):
        with self.assertRaises(BaseParserError):
            self.load("001", "001")
        self.assertFalse(ParserProductUrl.objects.exists())
