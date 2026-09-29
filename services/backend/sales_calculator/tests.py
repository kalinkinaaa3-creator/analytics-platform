import io
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest import TestCase as UnitTestCase
from unittest.mock import Mock, patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from dashboards.models import Dashboard, DashboardAccess
from .api import SettingsView, RefreshView, ProductsView
from .calculation import calculate
from .configuration import DEFAULTS, validate_config
from .export import export_document
from .models import SalesCalculatorRefresh
from .warehouse import decorate


def product(**changes):
    return {"product_key": 1, "code": 123, "name": "Товар", "region": "Москва",
            "name_1c": "Товар 1С", "price_list": "Товар прайса", "calculation_date": "2026-09-30",
            "retail": "100", "small": "90", "medium": "80", "large": "70",
            "characteristics": {}, "logistics": {}, "stocks": {}, "weight_value": "2", "pallet_value": "50", **changes}


class CalculationTests(UnitTestCase):
    def run_order(self, quantity, **changes):
        return calculate({"1": product(**changes)}, [{"product_key": 1, "quantity": quantity}], {})

    def test_strict_threshold_and_reprice_whole_order(self):
        self.assertEqual(self.run_order(500)["automatic_type"], "retail")
        result = self.run_order(501)
        self.assertEqual(result["automatic_type"], "small")
        self.assertEqual(result["net"], Decimal("45090.00"))
        # Reprice sequentially: retail > 300000 does not by itself imply medium.
        self.assertEqual(self.run_order(3200)["automatic_type"], "small")
        self.assertEqual(self.run_order(10000)["automatic_type"], "medium")
        self.assertEqual(self.run_order(10001)["automatic_type"], "large")

    def test_manual_types_do_not_change_recommendation(self):
        products = {"1": product(), "2": product(product_key=2)}
        items = [{"product_key": 1, "quantity": 300, "price_type": "large"}, {"product_key": 2, "quantity": 300}]
        result = calculate(products, items, {})
        self.assertEqual(result["automatic_type"], "small")
        self.assertTrue(result["manual"])
        self.assertEqual(result["net"], Decimal("48000"))
        self.assertEqual(result["gross"], Decimal("58560"))

    def test_vat_rounding_and_warning(self):
        for mode, expected in (("none", "100.5"), ("half_up", "101"), ("floor", "100"), ("ceil", "101")):
            result = calculate({"1": product(retail="100.5")}, [{"product_key": 1, "quantity": 1}], {"rounding": mode, "vat": 0})
            self.assertEqual(result["net"], Decimal(expected))
            self.assertEqual(result["vat"], 0)
        result = self.run_order(40000)
        self.assertTrue(result["warning"])
        self.assertEqual(result["automatic_type"], "large")

    def test_missing_price_invalid_numbers_and_duplicate_rejected(self):
        for value in (None, "NaN", "Infinity", "-1"):
            with self.assertRaises(ValueError): self.run_order(1, retail=value)
        for quantity in (0, -1, "NaN"):
            with self.assertRaises(ValueError): self.run_order(quantity)
        with self.assertRaises(ValueError):
            calculate({"1": product()}, [{"product_key": 1}, {"product_key": 1}], {})
        with self.assertRaises(ValueError): validate_config({"thresholds": [50, 50, 800]})

    def test_missing_logistics_is_not_zero(self):
        result = self.run_order(100, weight_value=None)
        self.assertIsNone(result["logistics"]["weight"])
        self.assertEqual(result["logistics"]["pallets"], 2)

    def test_characteristics_and_logistics_mapping(self):
        row = decorate(product(color="Черный", nom_cn_fea="3923", quantity_eurotruck=600), {
            "Длина (Глубина), мм": "600", "Ширина, мм": "400", "Высота, мм": "200",
            "Объём, л": "7,5", "Объем, л": "8", "Перфорация стенок": "Нет",
            "Способ сложения (коробка)": "120", "Вес, кг": "1,5", "Складирование": "60"})
        self.assertEqual(row["characteristics"]["dimensions"], "600 × 400 × 200")
        self.assertEqual(row["characteristics"]["volume"], "7,5")
        self.assertNotIn("perforation", row["characteristics"])
        self.assertEqual(row["logistics"]["packing"], "по 120 шт./короб")
        self.assertEqual(row["logistics"]["tnved"], "3923")

    def test_xlsx_embeds_photo_and_does_not_execute_names(self):
        from PIL import Image
        from openpyxl import load_workbook
        image = io.BytesIO(); Image.new("RGB", (10, 10), "white").save(image, format="PNG")
        result = calculate({"1": product(name="=1+1", image="https://iplast.com/a.png")}, [{"product_key": 1}], {})
        config = validate_config({"full_columns": ["image", "name", "unit_net", "url"]})
        with patch("sales_calculator.export.image_bytes", return_value=image.getvalue()):
            document = export_document(result, config, "full", "xlsx")
        self.assertTrue(any(n.startswith("xl/media/") for n in ZipFile(document).namelist()))
        document.seek(0); ws = load_workbook(document).active
        self.assertEqual(ws["B4"].data_type, "s")
        self.assertEqual(ws["B4"].value, "=1+1")

    def test_pdf_and_simple_column_selection(self):
        result = self.run_order(1)
        config = validate_config({"simple_columns": ["name", "retail_net", "retail_gross"]})
        pdf = export_document(result, config, "simple", "pdf")
        self.assertEqual(pdf.read(4), b"%PDF")
        from openpyxl import load_workbook
        ws = load_workbook(export_document(result, config, "simple", "xlsx")).active
        self.assertEqual(ws.max_column, 3)
        self.assertIn("50000", ws["B3"].value)

    def test_pdf_photo_only_without_available_image(self):
        document = export_document(self.run_order(1), validate_config({"simple_columns": ["image"]}), "simple", "pdf")
        self.assertEqual(document.read(4), b"%PDF")


class PublicationTests(UnitTestCase):
    def publish_with_client(self, client, rows=None):
        from .warehouse import publish
        with patch("django.db.transaction.atomic"), patch("sales_calculator.warehouse.connection"), patch("sales_calculator.warehouse.build_rows", return_value=rows or []), patch("sales_calculator.warehouse.get_clickhouse_client", return_value=client):
            return publish(date(2026, 9, 30), False)

    def test_insert_has_named_metadata_and_unavailable_stock_before_exchange(self):
        import json
        from .warehouse import COLUMNS
        client = Mock()
        row = product(distr=None, distr_1=None, stocks=None, quantity_eurotruck=240)
        self.assertEqual(self.publish_with_client(client, [row]), 1)
        calls = client.execute.call_args_list
        insert_index = next(i for i, call in enumerate(calls) if call.args[0].startswith("INSERT"))
        values = calls[insert_index].args[1][0]
        self.assertEqual(len(values), len(COLUMNS.split(", ")))
        inserted = dict(zip(COLUMNS.split(", "), values))
        self.assertEqual(inserted["name"], row["name"])
        self.assertEqual(inserted["quantity_eurotruck"], Decimal(240))
        self.assertIsNone(json.loads(inserted["stocks"]))
        self.assertTrue(calls[insert_index + 1].args[0].startswith("EXCHANGE"))

    def test_swap_failure_preserves_original_error_and_cleans_staging(self):
        client = Mock()
        def execute(sql):
            if sql.startswith("EXCHANGE"):
                raise RuntimeError("exchange failed")
        client.execute.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, "exchange failed"):
            self.publish_with_client(client)
        self.assertTrue(client.execute.call_args.args[0].startswith("DROP TABLE IF EXISTS default.sales_calculator_product_build_"))

    def test_cleanup_failure_does_not_report_successful_publication_as_failed(self):
        client = Mock()
        def execute(sql):
            if sql.startswith("DROP"):
                raise RuntimeError("cleanup failed")
        client.execute.side_effect = execute
        self.assertEqual(self.publish_with_client(client), 0)


class AccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="viewer")
        self.other = get_user_model().objects.create_user(username="other")
        self.dashboard = Dashboard.objects.create(name="Commercial Price", slug="commercial-price")
        DashboardAccess.objects.create(user=self.user, dashboard=self.dashboard, can_view=True, can_edit=False)
        self.factory = APIRequestFactory()

    def request(self, method, view, user=None, data=None):
        request = getattr(self.factory, method)("/", data=data or {}, format="json")
        force_authenticate(request, user=user or self.user)
        return view.as_view()(request)

    def test_viewer_can_save_own_settings_but_cannot_refresh(self):
        self.assertEqual(self.request("put", SettingsView, data={"vat": 0}).status_code, 200)
        self.assertEqual(self.request("get", SettingsView).data["config"]["vat"], 0)
        self.assertEqual(self.request("post", RefreshView).status_code, 403)
        DashboardAccess.objects.create(user=self.other, dashboard=self.dashboard, can_view=True)
        self.assertEqual(self.request("get", SettingsView, user=self.other).data["config"]["vat"], 22)

    def test_no_access_cannot_read_products_or_settings(self):
        self.assertEqual(self.request("get", SettingsView, user=self.other).status_code, 403)
        with patch("sales_calculator.api.read_products") as read:
            self.assertEqual(self.request("get", ProductsView, user=self.other).status_code, 403)
            read.assert_not_called()

    def test_old_stock_hidden(self):
        with patch("sales_calculator.api.read_products", return_value=[product(calculation_date="2000-01-01", stocks={"A": 7})]), patch("sales_calculator.api.state_payload", return_value={}):
            response = self.request("get", ProductsView)
        self.assertTrue(response.data["stale"])
        self.assertIsNone(response.data["products"][0]["stocks"])


class RefreshTests(TestCase):
    def test_price_failure_preserves_mart_and_skips_stock(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True, refresh_sources=True)
        cursor = Mock(); cursor.fetchone.return_value = [True]
        with patch("sales_calculator.refresh.connection") as conn, patch("datasets.services.external_api.price_api_loader.load_prices_from_api", side_effect=RuntimeError("1C unavailable")), patch("datasets.services.external_api.stock_api_loader.load_stocks_from_api") as stock, patch("sales_calculator.warehouse.publish") as publish:
            conn.cursor.return_value.__enter__.return_value = cursor
            drain()
        stock.assert_not_called(); publish.assert_not_called()
        self.assertEqual(SalesCalculatorRefresh.objects.get(pk=1).status, "failed")

    def test_stock_failure_publishes_without_stock(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True, refresh_sources=True)
        cursor = Mock(); cursor.fetchone.return_value = [True]
        with patch("sales_calculator.refresh.connection") as conn, patch("datasets.services.external_api.price_api_loader.load_prices_from_api"), patch("datasets.services.external_api.stock_api_loader.load_stocks_from_api", side_effect=RuntimeError("stock unavailable")), patch("datasets.models.NomenclaturePrice.objects.filter") as price, patch("datasets.models.NomenclatureStock.objects.filter") as stock, patch("sales_calculator.warehouse.publish", return_value=5) as publish:
            conn.cursor.return_value.__enter__.return_value = cursor
            price.return_value.exists.return_value = True; stock.return_value.exists.return_value = True
            drain()
        publish.assert_called_once_with(timezone.localdate(), False)
        state = SalesCalculatorRefresh.objects.get(pk=1)
        self.assertEqual(state.status, "success")
        self.assertFalse(state.stock_available)
        self.assertIsNotNone(state.stock_failed_at)

    def test_concurrent_worker_does_not_consume_request(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True)
        cursor = Mock(); cursor.fetchone.return_value = [False]
        with patch("sales_calculator.refresh.connection") as conn, patch("sales_calculator.warehouse.publish") as publish:
            conn.cursor.return_value.__enter__.return_value = cursor
            drain()
        publish.assert_not_called()
        self.assertTrue(SalesCalculatorRefresh.objects.get(pk=1).requested)

    def test_request_during_publication_is_processed_before_unlock(self):
        from .refresh import drain
        SalesCalculatorRefresh.objects.create(pk=1, requested=True)
        cursor = Mock(); cursor.fetchone.return_value = [True]
        calls = []
        def publish(*args):
            calls.append(args)
            if len(calls) == 1:
                SalesCalculatorRefresh.objects.filter(pk=1).update(requested=True)
            return 2
        with patch("sales_calculator.refresh.connection") as conn, patch("datasets.models.NomenclaturePrice.objects.filter") as price, patch("datasets.models.NomenclatureStock.objects.filter") as stock, patch("sales_calculator.warehouse.publish", side_effect=publish):
            conn.cursor.return_value.__enter__.return_value = cursor
            price.return_value.exists.return_value = True
            stock.return_value.exists.return_value = True
            drain()
        self.assertEqual(len(calls), 2)
        self.assertEqual(sum("pg_advisory_unlock" in str(call) for call in cursor.execute.call_args_list), 1)
        self.assertFalse(SalesCalculatorRefresh.objects.get(pk=1).requested)
