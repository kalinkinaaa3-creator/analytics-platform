from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from openpyxl import Workbook

from datasets.models import ProductCost as LegacyCost, TransportCost as LegacyTransport
from datasets.services.iprice_upload_template_export import UPLOAD_TEMPLATE_HEADERS
from organizations.models import Organization
from .iprice_domain_models import ParserPrefix, ParserProductUrl, ParserProductClassification, BaseProductPrice
from .iprice_models import IPriceSourceImport, IPriceRegionalInput
from .iprice_sources import import_source


def excel(kind, *rows):
    book = Workbook()
    from .iprice_purchase_import import HEADERS as PURCHASE_HEADERS
    from .iprice_regional_import import HEADERS as PARAMETER_HEADERS
    book.active.append(PURCHASE_HEADERS if kind == 'product_cost' else PARAMETER_HEADERS if kind == 'calculation_config' else UPLOAD_TEMPLATE_HEADERS[kind])
    for row in rows:
        book.active.append(row)
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


class SourceTests(TestCase):
    def test_new_classification_headers_round_trip_without_shifting_values(self):
        from openpyxl import load_workbook
        from .iprice_templates import export_template
        product = ParserProductUrl.objects.create(source='base', own_code='001', status='active')
        ParserProductClassification.objects.create(product_key=product.pk, category='Type value', subcategory='Category value',
            subcategory_type='Subcategory value', color='Green', material='PP', article_number_analogs='GROUP', item_type='product')
        book = load_workbook(export_template('product_classification'))
        headers = [cell.value for cell in book.active[1]]
        self.assertEqual(headers[1:4], ['type', 'category', 'subcategory'])
        self.assertNotIn('subcategory_type', headers)
        self.assertFalse(set(headers) & {'code_1c', 'name', 'on_website'})
        self.assertFalse(any(value is not None for row in book.active.iter_rows(min_row=2, values_only=True) for value in row))
        for column, value in enumerate([product.pk, 'Updated type', 'Updated category', 'Updated subcategory', 'Green', 'PP', '', 'GROUP', 'product'], 1):
            book.active.cell(2, column, value)
        content = BytesIO()
        book.save(content)
        book.close()
        import_source(content.getvalue(), kind='product_classification', filename='classification.xlsx',
                      user=self.user, organization=self.organization)
        saved = ParserProductClassification.objects.get(product_key=product.pk)
        self.assertEqual((saved.category, saved.subcategory, saved.subcategory_type),
                         ('Updated type', 'Updated category', 'Updated subcategory'))
        original = load_workbook(BytesIO(bytes(IPriceSourceImport.objects.latest('id').content)))
        self.assertEqual(original.active.cell(1, 2).value, 'type')
        original.close()

    def test_retired_uploads_rejected_without_writes(self):
        for kind in ('nomenclature', 'transport_cost'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.load(kind)
        self.assertFalse(IPriceSourceImport.objects.exists())

    def setUp(self):
        self.organization = Organization.objects.create(code="select-market", name="SM", postgres_schema="select_market")
        self.user = get_user_model().objects.create_user(username="source-editor")

    def load(self, kind, *rows):
        content = excel(kind, *rows)
        return import_source(content, kind=kind, filename="source.xlsx", user=self.user, organization=self.organization)



    def test_cost_text_code_full_replacement_and_legacy_isolation(self):
        LegacyCost.objects.create(date=date(2026, 10, 1), code=1, departure="Plant", cost=999)
        self.load("product_cost", ["2026-10-10", "001-А", "Product", "Plant", 100])
        row = IPriceRegionalInput.objects.get()
        self.assertEqual(row.code, "001-А")
        self.assertEqual(row.month, date(2026, 10, 1))
        self.load("product_cost", ["2026-11-01", "NEW", "Product", "Plant", 200])
        self.assertEqual(IPriceRegionalInput.objects.get(month=date(2026, 11, 1)).code, "NEW")
        self.assertEqual(LegacyCost.objects.get().cost, 999)
        self.assertEqual(IPriceSourceImport.objects.count(), 2)
        batch = IPriceSourceImport.objects.order_by("id").first()
        self.assertTrue(bytes(batch.content).startswith(b"PK"))
        self.assertEqual(batch.user, self.user)

    def test_duplicate_purchase_pair_is_rejected(self):
        with self.assertRaises(ValueError):
            self.load("product_cost", ["2026-10-01", "A", "Product", "Region", 10], ["2026-10-02", "A", "Product", "Region", 20])
        self.assertFalse(IPriceRegionalInput.objects.exists())

    def test_invalid_row_never_partially_replaces_costs(self):
        self.load("product_cost", ["2026-10-01", "A", "Product", "Plant", 10])
        for value in (123, None, ""):
            with self.subTest(code=value), self.assertRaises(ValueError):
                self.load("product_cost", ["2026-10-01", "B", "Product", "Plant", 20], ["2026-10-01", value, "Bad", "Plant", 30])
        self.assertEqual(IPriceRegionalInput.objects.get().code, "A")
        self.assertEqual(IPriceSourceImport.objects.count(), 1)


    def test_prefixes_define_only_local_regions(self):
        self.load("parser_prefixes", ["tara", "spb", "Region"])
        self.assertEqual(ParserPrefix.objects.get().shipp_region, "Region")
        with self.assertRaises(ValueError):
            self.load("parser_prefixes", ["unknown", "x", "Other"])
        self.assertEqual(ParserPrefix.objects.get().source, "tara")

    def test_regional_parameters_do_not_require_a_website_or_classification(self):
        self.load('product_cost', ['2026-10-01', '001-A', 'Product', 'Region', 100])
        parameters = ['2026-10-01', '001-A', 'Region', 1, .3, .1, .1, .15, .2, 1, 12.34]
        self.load('calculation_config', parameters)
        self.load('product_cost', ['2026-10-01', '001-A', 'Product', 'Region', 120])
        row = IPriceRegionalInput.objects.get()
        self.assertEqual(row.purchase_cost, 120)
        self.assertTrue(row.include_transport)
        self.assertEqual(str(row.logistics_unit), '12.34')
        self.assertFalse(ParserProductUrl.objects.exists())
        self.load('product_cost', ['2026-10-01', 'OTHER', 'Product', 'Region', 50])
        row.refresh_from_db()
        self.assertIsNone(row.purchase_cost)
        self.assertTrue(row.include_transport)
        self.assertEqual(IPriceRegionalInput.objects.count(), 2)

    def test_audit_failure_rolls_back_import(self):
        self.load("product_cost", ["2026-10-01", "A", "Product", "Region", 100])
        with patch.object(IPriceSourceImport.objects, "create", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.load("product_cost", ["2026-10-01", "A", "Product", "Region", 200])
        self.assertEqual(IPriceRegionalInput.objects.get().purchase_cost, 100)

    def test_formula_and_nonfinite_cost_rejected(self):
        for amount in ("=10+1", "NaN", "Infinity", -1):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.load("product_cost", ["2026-10-01", "A", "Product", "Region", amount])
        self.assertFalse(IPriceRegionalInput.objects.exists())

    def test_other_organization_rejected(self):
        self.organization.code, self.organization.postgres_schema = "iplast", "public"
        with self.assertRaises(ValueError):
            self.load("product_cost", ["2026-10-01", "A", "Product", "Region", 100])

    def test_api_editor_upload_and_viewer_denial(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .iprice_api import SourceFileView
        content = excel("product_cost", ["2026-10-01", "A", "Product", "Region", 100])
        for allowed, expected in [(False, 403), (True, 200)]:
            request = APIRequestFactory().post("/sources/product_cost/", {"file": SimpleUploadedFile("source.xlsx", content)}, format="multipart")
            request.organization = self.organization
            force_authenticate(request, user=self.user)
            with patch("select_market.iprice_api.Dashboard.objects") as dashboards, patch("select_market.iprice_api.user_can_edit_dashboard", return_value=allowed):
                dashboards.filter.return_value.first.return_value = object()
                response = SourceFileView.as_view()(request, kind="product_cost")
            self.assertEqual(response.status_code, expected)
        self.assertEqual(IPriceRegionalInput.objects.get().purchase_cost, 100)

    def test_legacy_cost_loader_keeps_numeric_codes(self):
        from datasets.services.product_cost_loader import load_product_cost_from_excel
        stream = BytesIO(excel("product_cost", ["2026-10-01", "001", "Product", "Plant", 10]))
        load_product_cost_from_excel(stream)
        self.assertEqual(LegacyCost.objects.get().code, 1)
        self.assertFalse(IPriceRegionalInput.objects.exists())

    def test_classification_matches_and_images_are_organization_local(self):
        from datasets.models import ParserProductClassification as LegacyClassification
        from .iprice_domain_models import ParserProductMatch
        base = ParserProductUrl.objects.create(source="base", url="https://example.test/base", status="active")
        competitor = ParserProductUrl.objects.create(source="tt", url="https://example.test/tt", status="active")
        legacy = LegacyClassification.objects.create(product_key=base.pk, category="Legacy", status="active")
        BaseProductPrice.objects.create(product_key=base.pk, code_1c="00-A", image="https://example.test/image", final_price=10)
        result = self.load("product_classification",
            [base.pk, "Box", "Sub", "Type", "Green", "PP", "", "GROUP", "product"],
            [competitor.pk, "Box", "Sub", "Type", "Green", "PP", "", "GROUP", "product"])
        self.assertEqual(result["automatic_matches_loaded"], 1)
        self.assertEqual(ParserProductMatch.objects.get().product_key_base, base.pk)
        self.assertEqual(ParserProductClassification.objects.get(product_key=base.pk).image, "https://example.test/image")
        legacy.refresh_from_db()
        self.assertEqual(legacy.category, "Legacy")
        self.assertEqual(legacy.status, "active")

    def test_unknown_classification_key_does_not_deactivate_existing(self):
        original = ParserProductClassification.objects.create(product_key=1, category="Original", status="active")
        with self.assertRaises(ValueError):
            self.load("product_classification", [999, "Box", "Sub", "Type", "Green", "PP", "", "GROUP", "product"])
        original.refresh_from_db()
        self.assertEqual(original.status, "active")
        self.assertFalse(IPriceSourceImport.objects.exists())

    def test_classification_expands_only_local_regional_groups(self):
        self.load("parser_prefixes", ["tara", "spb", "SPB"], ["tara", "msk", "MSK"])
        first = ParserProductUrl.objects.create(source="tara", prefix="spb", url="https://spb.example.test/product", status="active")
        second = ParserProductUrl.objects.create(source="tara", prefix="msk", url="https://msk.example.test/product", status="active")
        result = self.load("product_classification", [first.pk, "Box", "Sub", "Type", "Green", "PP", "", "GROUP", "product"])
        self.assertEqual(result["classifications_loaded"], 2)
        self.assertSetEqual(set(ParserProductClassification.objects.values_list("product_key", flat=True)), {first.pk, second.pk})

    def test_legacy_classification_loader_does_not_write_select_market(self):
        from datasets.models import ParserProductUrl as LegacyUrl, ParserProductClassification as LegacyClassification
        from datasets.services.parsers.product_classification_match_loader import load_product_classification_matches
        url = LegacyUrl.objects.create(source="base", url="https://example.test/legacy", status="active")
        result = load_product_classification_matches(BytesIO(excel("product_classification",
            [url.pk, "Box", "Sub", "Type", "Green", "PP", "", "GROUP", "product"])))
        self.assertEqual(result["classifications_loaded"], 1)
        self.assertEqual(LegacyClassification.objects.get().product_key, url.pk)
        self.assertFalse(ParserProductClassification.objects.exists())

    def test_classification_preserves_manual_matches_and_exclusions(self):
        from .iprice_domain_models import ParserProductMatch, IPriceCompetitorSelectionOverride
        base, first, second = [ParserProductUrl.objects.create(source=source, url=f"https://example.test/{i}", status="active")
            for i, source in enumerate(["base", "tt", "ps"])]
        manual = ParserProductMatch.objects.create(product_key_base=base.pk, product_key_competitor=first.pk, match_type="manual", status="active")
        IPriceCompetitorSelectionOverride.objects.create(product_key_base=base.pk, product_key_competitor=second.pk, selection_mode="exclude")
        result = self.load("product_classification", *[
            [url.pk, "Box", "Sub", "Type", "Green", "PP", "", "GROUP", "product"] for url in (base, first, second)])
        manual.refresh_from_db()
        self.assertEqual(manual.match_type, "manual")
        self.assertEqual(manual.status, "active")
        self.assertEqual(result["excluded_matches_preserved"], 1)
        self.assertEqual(result["automatic_matches_loaded"], 0)
