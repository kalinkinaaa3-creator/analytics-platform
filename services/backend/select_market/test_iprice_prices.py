from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from openpyxl import Workbook

from organizations.models import Organization
from .iprice_models import IPricePriceImport, NomenclaturePrice
from .iprice_prices import COLUMNS, PriceImportError, import_price_file, prices_as_of


def workbook(*rows):
    book = Workbook()
    book.active.append(COLUMNS)
    for day, code, price in rows:
        book.active.append([code, "Region", "Product", "Leaf", "Parent", "Root", None, price, price, price, price])
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


class PriceImportTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")
        self.user = get_user_model().objects.create_user(username="price-editor")

    def load(self, *rows):
        return import_price_file(workbook(*rows), filename="prices.xlsx", user=self.user, organization=self.organization,
                                 price_date=rows[0][0] if rows else "2026-10-01")

    def test_text_codes_original_gross_and_rounded_net_prices(self):
        self.load(("2026-10-01", "001-Ab", "1 220,25"))
        price = NomenclaturePrice.objects.get()
        self.assertEqual(price.code, "001-Ab")
        self.assertEqual(str(price.retail_gross), "1220.2500")
        self.assertEqual(str(price.retail), "1000.0000")
        self.assertEqual([price.group_1, price.group_2, price.group_3, price.group_4], ['Root', 'Parent', 'Leaf', ''])

    def test_rounding_is_half_up_in_both_directions(self):
        from .iprice_prices import price_with_vat
        self.load(("2026-10-01", "001", "1615"))
        self.assertEqual(NomenclaturePrice.objects.get().retail, 1324)
        self.assertEqual(price_with_vat(1324), 1615)
        self.assertEqual(price_with_vat(25), 31)
        self.load(("2026-10-01", "001", "122.61"))
        self.assertEqual(NomenclaturePrice.objects.get().retail, 101)

    def test_date_required_and_same_file_can_be_loaded_for_another_day(self):
        from .iprice_prices import parse_price_file
        content = workbook(("2026-10-01", "001", 122))
        for value in (None, '', 'invalid'):
            with self.assertRaises(PriceImportError):
                parse_price_file(content, price_date=value)
        for day in ('2026-10-01', '2026-10-02'):
            import_price_file(content, filename='p.xlsx', user=self.user, organization=self.organization, price_date=day)
        self.assertEqual(IPricePriceImport.objects.count(), 2)

    def test_complete_replacement_and_no_individual_fallback(self):
        self.load(("2026-10-01", "old", 100))
        self.load(("2026-10-02", "new", 200))
        self.assertEqual(list(prices_as_of(date(2026, 10, 3)).values_list("code", flat=True)), ["new"])
        self.load(("2026-10-02", "replacement", 300))
        self.assertEqual(NomenclaturePrice.objects.count(), 2)
        self.assertEqual(IPricePriceImport.objects.get(date="2026-10-02").revision, 2)
        self.assertEqual(prices_as_of(date(2026, 10, 1)).get().code, "old")

    def test_repeated_file_is_idempotent(self):
        content = workbook(("2026-10-01", "001", 100))
        for _ in range(2):
            batch = import_price_file(content, filename="p.xlsx", user=self.user, organization=self.organization, price_date="2026-10-01")
        self.assertEqual(batch.revision, 1)
        self.assertEqual(NomenclaturePrice.objects.count(), 1)

    def test_invalid_files_do_not_replace_published_prices(self):
        self.load(("2026-10-01", "valid", 100))
        bad_rows = [
            [("2026-10-01", 123, 100)],
            [("2026-10-01", "a", "=1+1")],
            [("2026-10-01", "a", -1)],
            [("2026-10-01", "a", 1), ("2026-10-01", "a", 2)],
            [],
        ]
        for rows in bad_rows:
            with self.subTest(rows=rows), self.assertRaises(PriceImportError):
                self.load(*rows)
        self.assertEqual(NomenclaturePrice.objects.get().code, "valid")

    def test_database_failure_rolls_back_replacement(self):
        self.load(("2026-10-01", "valid", 100))
        with patch.object(NomenclaturePrice.objects, "bulk_create", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.load(("2026-10-01", "new", 200))
        self.assertEqual(NomenclaturePrice.objects.get().code, "valid")
        self.assertEqual(IPricePriceImport.objects.get().revision, 1)

    def test_other_organization_rejected(self):
        self.organization.code = "iplast"
        with self.assertRaises(PriceImportError):
            self.load(("2026-10-01", "a", 1))

    def test_api_requires_edit_access_for_upload(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .iprice_api import PriceFileView
        request = APIRequestFactory().post("/price-file/", {})
        request.organization = self.organization
        force_authenticate(request, user=self.user)
        with patch("select_market.iprice_api.Dashboard.objects") as dashboards, patch("select_market.iprice_api.user_can_edit_dashboard", return_value=False):
            dashboards.filter.return_value.first.return_value = object()
            response = PriceFileView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(IPricePriceImport.objects.exists())

    def test_viewer_can_download_template(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .iprice_api import PriceFileView
        request = APIRequestFactory().get("/price-file/")
        request.organization = self.organization
        force_authenticate(request, user=self.user)
        with patch("select_market.iprice_api.Dashboard.objects") as dashboards, patch("select_market.iprice_api.user_can_view_dashboard", return_value=True):
            dashboards.filter.return_value.first.return_value = object()
            response = PriceFileView.as_view()(request)
        self.assertEqual(response.status_code, 200)
