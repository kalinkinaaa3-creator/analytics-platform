from datetime import date
from io import BytesIO, StringIO
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from openpyxl import load_workbook
from organizations.models import Organization
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers.base_parser import sync_base_urls
from .iprice_domain_models import BaseProductPrice, ParserProductUrl, ParserProductClassification, IPriceSnapshot
from .iprice_models import IPricePriceImport
from .iprice_prices import import_price_file, PriceImportError
from .iprice_registry import reconcile
from .iprice_catalog import build_products
from .iprice_templates import export_template
from .test_iprice_prices import workbook
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connection, close_old_connections
from django.test import TransactionTestCase


class RegistryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.ws = IPriceWorkspace('select-market')

    def price(self, codes=('001-A',), day='2026-10-01'):
        return import_price_file(workbook(*[(day, code, 122) for code in codes]), filename='price.xlsx',
                                 user=None, organization=self.org, price_date=day)

    def site(self, codes=('001-A',), complete=True, suffix=''):
        offers = [{'code_1c': code, 'url': f'https://example.test/{code}{suffix}'} for code in codes]
        sync_base_urls(offers, workspace=self.ws, deactivate_missing=complete)
        return offers

    def test_price_only_classification_without_fabricated_website_data(self):
        self.price(('001-A', '002'))
        record = ParserProductUrl.objects.get(own_code='001-A')
        self.assertTrue(record.in_price)
        self.assertFalse(record.on_website)
        self.assertIsNone(record.url)
        self.assertFalse(BaseProductPrice.objects.exists())
        ParserProductClassification.objects.create(product_key=record.pk, category='Boxes', item_type='product')
        snapshot = IPriceSnapshot.objects.create(calculation_date=date(2026, 10, 1), version_number=1, revision_for_date=1)
        build_products(snapshot)
        product = snapshot.products.get(code_1c='001-A')
        self.assertEqual(product.base_product_key, record.pk)
        self.assertTrue(product.is_classified)
        self.assertEqual(product.category, 'Boxes')
        self.assertIn('MISSING_WEBSITE_PRODUCT', product.warning_codes)
        self.assertNotIn('MISSING_CLASSIFICATION', product.warning_codes)

    def test_price_only_product_uses_saved_competitor_links(self):
        from datetime import datetime, timezone
        from .iprice_domain_models import ParserProductMatch, TtProductPrice
        self.price()
        own = ParserProductUrl.objects.get()
        ParserProductClassification.objects.create(product_key=own.pk, category='Boxes', item_type='product')
        competitor = ParserProductUrl.objects.create(source='tt', url='https://example.test/competitor', prefix='-')
        ParserProductMatch.objects.create(product_key_base=own.pk, product_key_competitor=competitor.pk, status='active', match_type='auto')
        price = TtProductPrice.objects.create(product_key=competitor.pk, final_price=100)
        TtProductPrice.objects.filter(pk=price.pk).update(date_add=datetime(2026, 10, 1, tzinfo=timezone.utc))
        snapshot = IPriceSnapshot.objects.create(calculation_date=date(2026, 10, 1), version_number=1, revision_for_date=1)
        build_products(snapshot)
        product = snapshot.products.get()
        self.assertEqual(product.pricing_method, 'analog')
        self.assertEqual(product.competitor_rrp_median, 100)
        self.assertEqual(product.competitors.get().competitor_product_key, competitor.pk)
        self.assertFalse(BaseProductPrice.objects.exists())

    def test_site_appearance_change_url_disappearance_and_return_keep_key(self):
        self.price()
        record = ParserProductUrl.objects.get()
        classification = ParserProductClassification.objects.create(product_key=record.pk, category='Boxes')
        self.site()
        self.site(suffix='/new')
        record.refresh_from_db()
        classification.refresh_from_db()
        self.assertTrue(record.on_website)
        self.assertTrue(record.url.endswith('/new'))
        self.assertEqual(classification.url, record.url)
        self.site(('OTHER',))
        record.refresh_from_db()
        self.assertFalse(record.on_website)
        self.assertEqual(record.status, 'active')
        self.price(('OTHER',), day='2026-10-02')
        record.refresh_from_db()
        self.assertEqual(record.status, 'inactive')
        self.site()
        record.refresh_from_db()
        self.assertEqual(record.status, 'active')
        self.assertEqual(ParserProductUrl.objects.get(own_code='001-A').pk, record.pk)
        classification.refresh_from_db()
        self.assertEqual(classification.status, 'active')

    def test_old_price_and_partial_site_do_not_deactivate_current_products(self):
        self.price(('NEW',), day='2026-10-03')
        self.price(('OLD',), day='2026-10-01')
        self.assertTrue(ParserProductUrl.objects.get(own_code='NEW').in_price)
        self.assertFalse(ParserProductUrl.objects.get(own_code='OLD').in_price)
        self.site(('NEW',))
        self.site(('OTHER',), complete=False)
        self.assertTrue(ParserProductUrl.objects.get(own_code='NEW').on_website)

    def test_existing_ids_backfill_dry_run_and_apply(self):
        record = ParserProductUrl.objects.create(source='base', url='https://example.test/old', is_loaded=True)
        BaseProductPrice.objects.create(product_key=record.pk, code_1c='0001')
        output = StringIO()
        call_command('reconcile_iprice_products', stdout=output)
        record.refresh_from_db()
        self.assertIsNone(record.own_code)
        self.assertIn('DRY RUN', output.getvalue())
        reconcile(apply=True)
        record.refresh_from_db()
        self.assertEqual(record.own_code, '0001')
        self.assertTrue(record.on_website)
        self.assertEqual(reconcile(apply=True)['bound'], 0)

    def test_ambiguous_existing_ids_fail_without_publishing_price(self):
        for suffix in ['a', 'b']:
            record = ParserProductUrl.objects.create(source='base', url=f'https://example.test/{suffix}')
            BaseProductPrice.objects.create(product_key=record.pk, code_1c='001-A')
        with self.assertRaises(PriceImportError):
            self.price()
        self.assertFalse(IPricePriceImport.objects.exists())
        self.assertFalse(ParserProductUrl.objects.filter(own_code__isnull=False).exists())

    def test_duplicate_xml_codes_rollback_and_unique_database_constraint(self):
        self.price()
        with self.assertRaises(ValueError):
            self.site(('001-A', '001-A'))
        self.assertFalse(ParserProductUrl.objects.get().on_website)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParserProductUrl.objects.create(source='base', own_code='001-A')

    def test_template_includes_own_product_without_url(self):
        self.price()
        book = load_workbook(export_template('product_classification'))
        rows = list(book.active.values)
        fields = dict(zip(rows[0], rows[1]))
        self.assertEqual(fields['product_key'], ParserProductUrl.objects.get().pk)
        self.assertEqual(fields['code_1c'], '001-A')
        self.assertEqual(fields['name'], 'Product')
        self.assertEqual(fields['on_website'], 'Нет')
        self.assertEqual(book.active.auto_filter.ref, f'A1:L2')
        book.close()

    def test_template_names_for_site_only_product_and_competitor(self):
        from .iprice_domain_models import TtProductPrice
        own = ParserProductUrl.objects.create(source='base', own_code='0001', on_website=True, url='https://example.test/own')
        BaseProductPrice.objects.create(product_key=own.pk, code_1c='0001', name='Site-only product')
        competitor = ParserProductUrl.objects.create(source='tt', url='https://example.test/competitor')
        TtProductPrice.objects.create(product_key=competitor.pk, name='Competitor name', final_price=100)
        ParserProductClassification.objects.create(product_key=competitor.pk, category='Boxes', item_type='product')
        book = load_workbook(export_template('product_classification'))
        rows = list(book.active.values)
        records = {row[0]: dict(zip(rows[0], row)) for row in rows[1:] if row[0]}
        self.assertEqual(records[own.pk]['name'], 'Site-only product')
        self.assertEqual(records[competitor.pk]['name'], 'Competitor name')
        self.assertEqual(book.active.cell(2, rows[0].index('code_1c') + 1).number_format, '@')
        book.close()

    def test_download_fill_upload_classification_without_site(self):
        from .iprice_sources import import_source
        self.price()
        book = load_workbook(export_template('product_classification'))
        headers = [cell.value for cell in book.active[1]]
        for field, value in {'type': 'Boxes', 'category': 'Plastic', 'subcategory': 'Small',
                             'article_number_analogs': '001', 'color': '-', 'item_type': 'product'}.items():
            book.active.cell(2, headers.index(field) + 1, value)
        output = BytesIO()
        book.save(output)
        book.close()
        import_source(output.getvalue(), kind='product_classification', filename='class.xlsx', user=None, organization=self.org)
        record = ParserProductUrl.objects.get()
        self.assertEqual(ParserProductClassification.objects.get(product_key=record.pk).category, 'Boxes')
        self.assertFalse(BaseProductPrice.objects.exists())

    def test_idempotent_price_and_manual_disabled_classification_stays_disabled(self):
        self.price()
        record = ParserProductUrl.objects.get()
        classification = ParserProductClassification.objects.create(product_key=record.pk, status='inactive')
        self.price()
        self.price(('OTHER',), day='2026-10-02')
        self.price(day='2026-10-03')
        self.assertEqual(ParserProductUrl.objects.get(own_code='001-A').pk, record.pk)
        classification.refresh_from_db()
        self.assertEqual(classification.status, 'inactive')

    def test_website_url_cannot_be_assigned_to_another_code(self):
        self.price()
        self.site()
        with self.assertRaises(ValueError):
            sync_base_urls([{'code_1c': 'OTHER', 'url': 'https://example.test/001-A'}], workspace=self.ws)
        self.assertEqual(ParserProductUrl.objects.get().own_code, '001-A')


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL acceptance database')
class RegistryConcurrencyTests(TransactionTestCase):
    def test_price_and_site_create_one_identity(self):
        org = Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        gate = Barrier(2)
        content = workbook(('2026-10-01', '001-A', 122))

        def load(site):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                if site:
                    sync_base_urls([{'code_1c': '001-A', 'url': 'https://example.test/product'}], workspace=IPriceWorkspace('select-market'))
                else:
                    import_price_file(content, filename='price.xlsx', user=None, organization=org, price_date='2026-10-01')
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(load, site) for site in (True, False)]
            for future in futures:
                future.result(timeout=30)
        record = ParserProductUrl.objects.get(source='base')
        self.assertEqual(record.own_code, '001-A')
        self.assertTrue(record.on_website)
        self.assertTrue(record.in_price)
