from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from datasets.services.iprice_workspace import DATA_MODELS, DASHBOARD_MODELS, RETIRED_SELECT_MARKET_MODELS, IPriceWorkspace, workspace_for
from datasets.services.iprice_source_selector import get_nomenclature_price, get_product_cost, get_all_sale_regions, get_competitor_price_data
from .iprice_models import IPricePriceImport


class WorkspaceTests(TestCase):
    def setUp(self):
        self.sm = IPriceWorkspace("select-market")
        self.old = IPriceWorkspace("iplast")

    def test_all_models_are_distinct_and_relations_stay_local(self):
        for name in (DATA_MODELS | DASHBOARD_MODELS) - RETIRED_SELECT_MARKET_MODELS:
            with self.subTest(name=name):
                model = self.sm.model(name)
                self.assertIsNot(model, self.old.model(name))
                self.assertNotEqual(model._meta.db_table, self.old.model(name)._meta.db_table)
                for field in model._meta.fields:
                    if field.is_relation:
                        self.assertIn(field.remote_field.model._meta.app_label, {"select_market", "auth"})

    def test_all_business_codes_are_text(self):
        for model, field in [("NomenclaturePrice", "code"), ("BaseProductPrice", "code_1c"), ("IPriceSnapshotProduct", "code_1c")]:
            self.assertEqual(self.sm.model(model)._meta.get_field(field).get_internal_type(), "CharField")
        self.assertEqual(self.sm.product_code(" 00-A "), "00-A")
        with self.assertRaises(ValueError):
            self.sm.product_code(12)

    def test_no_implicit_fallback_for_unknown_organization(self):
        for code, schema in [("other", "public"), ("select-market", "public")]:
            with self.assertRaises(ValueError):
                workspace_for(SimpleNamespace(code=code, postgres_schema=schema))

    def test_price_selection_isolated_and_whole_date(self):
        day = date(2026, 10, 1)
        self.old.model("NomenclaturePrice").objects.create(date=day, code=1, shipp_region="Region", retail=999)
        batch = IPricePriceImport.objects.create(date=day, rows=1, filename="p.xlsx", checksum="a")
        self.sm.model("NomenclaturePrice").objects.create(date=day, code="001", shipp_region="Region", retail=100, batch=batch)
        self.assertEqual(get_nomenclature_price(code=1, shipp_region="Region", calculation_date=day).retail, Decimal(999))
        self.assertEqual(get_nomenclature_price(code="001", shipp_region="Region", calculation_date=day, workspace=self.sm).retail, Decimal(100))
        IPricePriceImport.objects.create(date=date(2026, 10, 2), rows=0, filename="p.xlsx", checksum="b")
        self.assertIsNone(get_nomenclature_price(code="001", shipp_region="Region", calculation_date=date(2026, 10, 3), workspace=self.sm))

    def test_shared_cost_selector_preserves_text_and_legacy_default(self):
        day = date(2026, 10, 1)
        for name in RETIRED_SELECT_MARKET_MODELS:
            with self.assertRaises(ValueError):
                self.sm.model(name)
        self.assertIsNone(get_product_cost(code=1, departure="Plant", calculation_date=day))

    def test_namespaces_differ(self):
        for kind in ("cache", "events", "files", "runs"):
            self.assertNotEqual(self.sm.namespace(kind), self.old.namespace(kind))

    def test_competitor_selection_uses_own_prices_even_when_ids_match(self):
        day = timezone.localdate()
        for workspace, amount in [(self.old, 500), (self.sm, 700)]:
            workspace.model("ParserProductUrl").objects.create(id=42, source="tara", url="https://example.test/item", prefix="-")
            workspace.model("TaraProductPrice").objects.create(product_key=42, url="https://example.test/item", final_price=amount)
        old = get_competitor_price_data(product_key=42, calculation_date=day)
        new = get_competitor_price_data(product_key=42, calculation_date=day, workspace=self.sm)
        self.assertEqual(old["calculation_price"], Decimal(500))
        self.assertEqual(new["calculation_price"], Decimal(700))

    def test_region_lists_do_not_mix(self):
        self.old.model("ParserPrefix").objects.create(source="tara", prefix="a", shipp_region="Old")
        self.sm.model("ParserPrefix").objects.create(source="tara", prefix="b", shipp_region="New")
        self.assertEqual(get_all_sale_regions(), ["Old"])
        self.assertEqual(get_all_sale_regions(workspace=self.sm), ["New"])
