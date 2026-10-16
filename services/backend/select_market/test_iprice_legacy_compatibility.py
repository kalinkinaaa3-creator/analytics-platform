"""Regression contracts for Iplast through the shared production services.

Uses isolated in-memory model mappings; no production DB or external requests.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook

from datasets import models as legacy
from datasets.services import iprice_snapshot_builder as builder
from datasets.services.iprice_snapshot_approval import create_iprice_snapshot_approval
from datasets.services.iprice_snapshot_export import export_iprice_snapshot_to_excel, get_effective_prices
from organizations.models import Organization
from .iprice_domain_models import IPriceSnapshot as SelectSnapshot, BaseProductPrice as SelectPrice
from .test_iprice_yml import xml


class IplastCompatibilityTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate()
        Organization.objects.create(code='iplast', name='Iplast', postgres_schema='public')
        Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.url = legacy.ParserProductUrl.objects.create(source='base', url='https://example.test/001', status='active')
        legacy.ParserProductClassification.objects.create(product_key=self.url.pk, item_type='product', status='active')
        legacy.BaseProductPrice.objects.create(product_key=self.url.pk, code_1c=1, final_price=200, name='Iplast product')
        legacy.Nomenclature.objects.create(nom_code=1, nom='Iplast product', quantity_eurotruck=100)
        legacy.NomenclaturePrice.objects.create(date=self.day, code=1, shipp_region='Region',
            retail=200, distr=150, distr_1=160, small=170, medium=180, large=190)
        legacy.ParserPrefix.objects.create(source='tara', prefix='r', shipp_region='Region')
        legacy.ProductCost.objects.create(date=self.day.replace(day=1), code=1, departure='Plant', cost=100)
        legacy.TransportCost.objects.create(departure='Plant', arrival='Region', cost=1000, is_active=True)
        legacy.IPriceCalculationConfig.objects.create(product_key=self.url.pk, departure='Plant', arrival='Region',
            base_analog=1, base_exclusive=Decimal('.4'), minimum_margin=Decimal('.1'), is_active=True)
        legacy.DepartureDiscount.objects.create(product_key=self.url.pk, departure='Plant', arrival='Region',
            distr=Decimal('.25'), distr_1=Decimal('.2'), small=Decimal('.15'),
            medium=Decimal('.1'), large=Decimal('.05'), is_active=True)

    def calculate(self):
        with patch.object(builder, 'send_bitrix_message'), patch('datasets.services.iprice_runtime.sync_snapshot_and_publish'):
            result = builder.build_iprice_snapshot(calculation_date=self.day)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(SelectSnapshot.objects.exists())
        return legacy.IPriceSnapshotRegion.objects.get()

    def test_full_legacy_calculation_keeps_routes_distributors_and_original_rounding(self):
        row = self.calculate()
        self.assertFalse(row.error_codes)
        self.assertEqual(row.departure, 'Plant')
        self.assertEqual(row.logistics_unit, Decimal('10'))
        self.assertEqual(row.cost_with_logistics, Decimal('110'))
        self.assertEqual(row.calculated_rrp, Decimal('183'))
        self.assertEqual(row.calculated_distr, Decimal('137.25'))
        self.assertEqual(row.calculated_distr_1, Decimal('146.4'))
        self.assertEqual(row.snapshot_product.effective_approved_rrp_median, row.calculated_rrp)

    def test_manual_legacy_price_is_not_subject_to_select_market_margin_or_whole_rubles(self):
        row = self.calculate()
        approval = create_iprice_snapshot_approval(snapshot_region=row, approved_rrp=Decimal('100.1234'), comment='Legacy decision')
        self.assertEqual(approval.approved_rrp, Decimal('100.1234'))
        self.assertEqual(approval.approved_distr, Decimal('75.0926'))
        self.assertEqual(approval.approved_small, Decimal('85.1049'))
        effective = get_effective_prices(row)
        self.assertEqual(effective['distr'], Decimal('75.0926'))
        self.assertEqual(effective['rrp'], Decimal('100.1234'))

    def test_legacy_export_keeps_six_prices_and_production_column(self):
        row = self.calculate()
        with export_iprice_snapshot_to_excel(snapshot=row.snapshot_product.snapshot) as stream:
            book = load_workbook(stream)
        headers = [cell.value for cell in book['Цены'][1]]
        self.assertTrue(any('Производство' in str(value) for value in headers))
        self.assertIn('Итоговая distr', headers)
        self.assertIn('Итоговая distr_1', headers)
        self.assertEqual(book['Цены'].cell(2, headers.index('Итоговая distr') + 1).value, 137.25)
        self.assertFalse(SelectSnapshot.objects.exists())
        book.close()

    @override_settings(PARSER_SHARED_QUEUE_ENABLED=False)
    def test_legacy_yml_loader_keeps_numeric_codes_and_own_tables_without_queue(self):
        from datasets.services.parsers.base_parser import load_base_products
        from datasets.parser_queue_models import ParserQueueEntry
        refresh = Mock()
        with patch('datasets.services.parsers.base_parser.fetch_yml_root', return_value=xml('001')), patch.dict(
                'sys.modules', {'sales_calculator.refresh': SimpleNamespace(source_updated=refresh)}):
            load_base_products()
        refresh.assert_called_once_with()
        self.assertEqual(legacy.BaseProductPrice.objects.latest('pk').code_1c, 1)
        self.assertFalse(SelectPrice.objects.exists())
        self.assertFalse(ParserQueueEntry.objects.exists())
