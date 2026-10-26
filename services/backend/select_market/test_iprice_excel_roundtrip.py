"""Download the actual API template, fill it, upload it and verify persistence."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from organizations.models import Organization
from .iprice_api import PriceFileView, SourceFileView, SnapshotExportView
from .iprice_models import NomenclaturePrice, IPriceRegionalInput, IPriceSourceImport
from .iprice_domain_models import ParserProductUrl, ParserProductClassification, ParserProductMatch, ParserPrefix, IPriceSnapshot


class ExcelRoundtripTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.user = get_user_model().objects.create_user(username='excel-editor')
        self.day = timezone.localdate()

    def request(self, kind, content=None):
        view, kwargs = (PriceFileView, {}) if kind == 'price' else (SourceFileView, {'kind': kind})
        request = APIRequestFactory().get('/') if content is None else APIRequestFactory().post('/', {
            'file': SimpleUploadedFile('filled.xlsx', content), 'price_date': self.day.isoformat()}, format='multipart')
        request.organization = self.organization
        force_authenticate(request, self.user)
        with patch('select_market.iprice_api.Dashboard.objects') as dashboards, patch('select_market.iprice_api.user_can_view_dashboard', return_value=True), patch('select_market.iprice_api.user_can_edit_dashboard', return_value=True):
            dashboards.filter.return_value.first.return_value = object()
            return view.as_view()(request, **kwargs)

    def filled(self, kind, rows):
        response = self.request(kind)
        self.assertEqual(response.status_code, 200)
        book = load_workbook(BytesIO(response.content))
        self.assertEqual(len(book.worksheets), 1)
        self.assertEqual(book.active.freeze_panes, 'A2')
        self.assertTrue(all(cell.comment for cell in book.active[1]))
        headers = [cell.value for cell in book.active[1]]
        self.assertFalse({'departure', 'distr', 'distr_1'} & set(headers))
        for header in ('Код', 'code', 'article_number_analogs', 'prefix'):
            if header in headers:
                self.assertEqual(book.active.cell(2, headers.index(header) + 1).number_format, '@')
        for r, values in enumerate(rows, 2):
            for c, value in enumerate(values, 1):
                book.active.cell(r, c, value)
        output = BytesIO()
        book.save(output)
        book.close()
        return output.getvalue()

    def upload(self, kind, *rows):
        result = self.request(kind, self.filled(kind, rows))
        self.assertEqual(result.status_code, 200, getattr(result, 'data', None))
        return result

    def price(self, code='001-A', region='Region'):
        return [code, region, 'Product', 'Deep', 'Boxes', 'Assortment', None, 'Active', 1220, 1464, 1615, 1342]

    def parameters(self, code='001-A', region='Region'):
        return [self.day.isoformat(), code, region, 1, '.3', '.1', '.1', '.15', '.2', 1, '12,34']

    def test_price_template_groups_vat_and_multiple_regions(self):
        self.upload('price', self.price(), self.price(region='Other'))
        self.assertEqual(NomenclaturePrice.objects.count(), 2)
        row = NomenclaturePrice.objects.get(shipp_region='Region')
        self.assertEqual(row.code, '001-A')
        self.assertEqual(row.assortment_matrix_status, 'Active')
        self.assertEqual((row.group_1, row.group_2, row.group_3, row.group_4), ('Assortment', 'Boxes', 'Deep', ''))
        self.assertEqual(row.retail_gross, Decimal('1615'))
        self.assertEqual(row.retail, Decimal('1324'))
        self.assertEqual((row.large, row.small, row.medium), (1000, 1200, 1100))

    def test_purchase_template_accepts_excel_dates_and_text_dates(self):
        self.upload('product_cost', [datetime.combine(self.day, datetime.min.time()), '001-A', 'Product', 'Region', '1 234,5678'],
                    [self.day.isoformat(), '00002', 'Other', 'Region', 0])
        self.assertEqual(IPriceRegionalInput.objects.get(code='001-A').purchase_cost, Decimal('1234.5678'))
        self.assertEqual(IPriceRegionalInput.objects.get(code='00002').purchase_cost, 0)

    def test_parameter_template_delivery_and_purchase_preservation(self):
        self.upload('product_cost', [self.day.isoformat(), '001-A', 'Product', 'Region', 100])
        self.upload('calculation_config', self.parameters())
        row = IPriceRegionalInput.objects.get()
        self.assertEqual(row.purchase_cost, 100)
        self.assertEqual(row.logistics_unit, Decimal('12.34'))
        self.assertTrue(row.include_transport)
        values = self.parameters(); values[-2:] = [0, None]
        self.upload('calculation_config', values)
        row.refresh_from_db()
        self.assertFalse(row.include_transport)
        self.assertIsNone(row.logistics_unit)
        self.assertEqual(row.purchase_cost, 100)

    def test_prefix_template_roundtrip(self):
        self.upload('parser_prefixes', ['tara', 'spb', 'Region'], ['tt', '-', 'Other'])
        self.assertEqual(set(ParserPrefix.objects.values_list('source', 'prefix')), {('tara', 'spb'), ('tt', '-')})

    def test_invalid_parameters_do_not_partially_replace_existing_inputs(self):
        self.upload('calculation_config', self.parameters())
        original = IPriceRegionalInput.objects.get()
        for amount in ('12.345', '=1+1', '-1'):
            bad = self.parameters('SECOND'); bad[-1] = amount
            changed = self.parameters(); changed[-1] = 99
            response = self.request('calculation_config', self.filled('calculation_config', [changed, bad]))
            self.assertEqual(response.status_code, 400)
            original.refresh_from_db()
            self.assertEqual(original.logistics_unit, Decimal('12.34'))
            self.assertEqual(IPriceRegionalInput.objects.count(), 1)

    def test_classification_template_preserves_text_analogue_group(self):
        base = ParserProductUrl.objects.create(source='base', url='https://example.test/base', status='active')
        other = ParserProductUrl.objects.create(source='tt', url='https://example.test/other', status='active')
        self.upload('product_classification', *[[url.pk, 'Box', 'Sub', 'Type', 'Green', 'PP', '', '00001', 'product'] for url in (base, other)])
        self.assertEqual(ParserProductClassification.objects.get(product_key=base.pk).article_number_analogs, '00001')
        self.assertEqual(ParserProductMatch.objects.get().product_key_competitor, other.pk)

    def test_empty_templates_are_rejected_without_import_audit(self):
        for kind in ('price', 'product_cost', 'calculation_config', 'parser_prefixes', 'product_classification'):
            with self.subTest(kind=kind):
                response = self.request(kind, self.filled(kind, []))
                self.assertEqual(response.status_code, 400)
        self.assertFalse(IPriceSourceImport.objects.exists())
        self.assertFalse(NomenclaturePrice.objects.exists())

    def test_invalid_price_does_not_replace_existing_full_price(self):
        self.upload('price', self.price())
        for code in (123, '=1+1'):
            result = self.request('price', self.filled('price', [self.price('NEW'), self.price(code)]))
            self.assertEqual(result.status_code, 400)
            self.assertEqual(list(NomenclaturePrice.objects.values_list('code', flat=True)), ['001-A'])

    def test_download_upload_calculation_export_cycle(self):
        from datasets.services import iprice_snapshot_builder as builder
        from datasets.services.iprice_workspace import IPriceWorkspace
        self.upload('price', self.price())
        self.upload('product_cost', [self.day.isoformat(), '001-A', 'Product', 'Region', 100])
        self.upload('calculation_config', self.parameters())
        with patch.object(builder, 'send_bitrix_message'), patch('datasets.services.iprice_runtime.sync_snapshot_and_publish'):
            builder.build_iprice_snapshot(calculation_date=self.day, workspace=IPriceWorkspace('select-market'))
        snapshot = IPriceSnapshot.objects.get()
        request = APIRequestFactory().get('/')
        request.organization = self.organization
        force_authenticate(request, self.user)
        with patch('select_market.iprice_api.Dashboard.objects') as dashboards, patch('select_market.iprice_api.user_can_view_dashboard', return_value=True):
            dashboards.filter.return_value.first.return_value = object()
            response = SnapshotExportView.as_view()(request, snapshot_id=snapshot.pk)
        self.assertEqual(response.status_code, 200)
        book = load_workbook(BytesIO(response.content))
        sheet = book['Цены']
        headers = [cell.value for cell in sheet[1]]
        cells = list(sheet[2])
        self.assertTrue(any(cell.value == '001-A' and cell.data_type == 's' for cell in cells))
        self.assertFalse(any('distr' in str(value) or 'Производство' in str(value) for value in headers))
        net = cells[headers.index('Розница, руб. без НДС')].value
        gross = cells[headers.index('Розница, руб. с НДС')].value
        self.assertEqual(net, 160)
        self.assertEqual(gross, 195)
        self.assertFalse(any(cell.data_type == 'f' for tab in book for row in tab for cell in row))
        book.close()
