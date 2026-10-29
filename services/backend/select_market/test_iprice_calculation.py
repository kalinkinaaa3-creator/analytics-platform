from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from organizations.models import Organization
from datasets.models import IPriceSnapshot as LegacySnapshot
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services import iprice_snapshot_builder as builder
from .iprice_domain_models import (ParserProductUrl, ParserProductClassification, BaseProductPrice,
    ParserPrefix,
    IPriceSnapshot, IPriceSnapshotRegion)
from .iprice_models import IPricePriceImport, NomenclaturePrice


class CalculationTests(TestCase):
    def setUp(self):
        Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.workspace = IPriceWorkspace('select-market')
        self.day = timezone.localdate()
        url = ParserProductUrl.objects.create(source='base', url='https://example.test/product', status='active')
        ParserProductClassification.objects.create(product_key=url.pk, item_type='product', status='active', modification='Old label', article_number_analogs='New label')
        BaseProductPrice.objects.create(product_key=url.pk, code_1c='00-А', final_price=100, name='Product')
        ParserPrefix.objects.create(source='tara', prefix='spb', shipp_region='Region')
        batch = IPricePriceImport.objects.create(date=self.day, filename='price.xlsx', checksum='test', rows=1)
        NomenclaturePrice.objects.create(batch=batch, date=self.day, shipp_region='Region', code='00-А', nom='Product', retail=100)
        from .iprice_models import IPriceRegionalInput
        IPriceRegionalInput.objects.create(month=self.day.replace(day=1), code='00-А', region='Region',
            purchase_cost=50, include_transport=True, logistics_unit=10, base_analog=1,
            base_exclusive=Decimal('.3'), minimum_margin=Decimal('.1'), small=Decimal('.1'),
            medium=Decimal('.1'), large=Decimal('.1'))

    def test_full_calculation_uses_text_code_and_isolated_models(self):
        with patch.object(builder, 'send_bitrix_message') as notify, patch('datasets.services.iprice_runtime.sync_snapshot_and_publish') as publish:
            result = builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        self.assertEqual(result['status'], 'success')
        product = IPriceSnapshot.objects.get().products.get()
        self.assertEqual(product.article_number_analogs, 'New label')
        self.assertEqual(product.modification, 'Old label')
        self.assertEqual(product.code_1c, '00-А')
        row = IPriceSnapshotRegion.objects.get()
        self.assertEqual(row.cost_with_logistics, Decimal('60'))
        self.assertEqual(product.current_retail_median, Decimal('100'))
        self.assertEqual(product.effective_approved_rrp_median, row.calculated_rrp)
        self.assertEqual(Decimal(product.calculation_details['effective_small_median']), row.calculated_small)
        self.assertFalse(LegacySnapshot.objects.exists())
        notify.assert_not_called()
        publish.assert_not_called()

    def test_failed_revision_preserves_previous_current(self):
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        first = IPriceSnapshot.objects.get()
        with patch('select_market.iprice_catalog.build_products', side_effect=ValueError('Invalid price list')), self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        first.refresh_from_db()
        self.assertTrue(first.is_current)
        self.assertEqual(IPriceSnapshot.objects.order_by('-id').first().status, 'failed')

    def test_excel_export_uses_local_rows_and_preserves_text(self):
        from openpyxl import load_workbook
        from datasets.services.iprice_snapshot_export import export_iprice_snapshot_to_excel
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        snapshot = IPriceSnapshot.objects.get()
        product = snapshot.products.get()
        product.nom = '=1+1'
        product.save(update_fields=['nom'])
        LegacySnapshot.objects.create(pk=snapshot.pk, calculation_date=self.day,
            version_number=1, revision_for_date=1, status='success')
        output = export_iprice_snapshot_to_excel(snapshot=snapshot)
        book = load_workbook(output)
        cells = [cell for sheet in book for row in sheet for cell in row]
        self.assertTrue(any(cell.value == '00-А' and cell.data_type == 's' for cell in cells))
        self.assertTrue(any(cell.value == '=1+1' and cell.data_type == 's' for cell in cells))
        self.assertFalse(any(cell.data_type == 'f' for cell in cells))
        prices = book['Цены']
        headers = [cell.value for cell in prices[1]]
        self.assertFalse(any('Дистриб' in label or 'Производство' in label for label in headers))
        net = prices.cell(2, headers.index('Розница, руб. без НДС') + 1)
        gross = prices.cell(2, headers.index('Розница, руб. с НДС') + 1)
        from .iprice_prices import price_with_vat
        self.assertEqual(gross.value, price_with_vat(Decimal(str(net.value))))
        self.assertEqual(net.number_format, '#,##0')
        book.close()
        output.close()

    def test_legacy_snapshot_creation_stays_in_legacy_table(self):
        builder.create_iprice_snapshot(calculation_date=self.day)
        self.assertTrue(LegacySnapshot.objects.exists())
        self.assertFalse(IPriceSnapshot.objects.exists())

    def test_missing_cost_is_an_explicit_row_error(self):
        from .iprice_models import IPriceRegionalInput
        IPriceRegionalInput.objects.all().delete()
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        row = IPriceSnapshotRegion.objects.get()
        self.assertEqual(row.calculation_status, 'error')
        self.assertIn('INVALID_PURCHASE_COST', row.error_codes)
        self.assertIsNone(row.cost_with_logistics)

    def test_second_build_is_rejected_until_first_finishes(self):
        builder.create_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        with self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.create_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        self.assertEqual(IPriceSnapshot.objects.count(), 1)

    def test_activation_does_not_change_iplast_active_version(self):
        legacy = LegacySnapshot.objects.create(calculation_date=self.day, version_number=1, revision_for_date=1, status='success', is_current=True, is_active=True)
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        builder.activate_iprice_snapshot(snapshot=IPriceSnapshot.objects.get())
        self.assertTrue(IPriceSnapshot.objects.get().is_active)
        legacy.refresh_from_db()
        self.assertTrue(legacy.is_active)

    def test_activation_is_idempotent_and_keeps_history(self):
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        first = builder.activate_iprice_snapshot(snapshot=IPriceSnapshot.objects.get())
        again = builder.activate_iprice_snapshot(snapshot=first)
        self.assertEqual(first.activated_at, again.activated_at)
        self.assertEqual(len(again.parameters['activation_history']), 1)
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        second = builder.activate_iprice_snapshot(snapshot=IPriceSnapshot.objects.latest('pk'))
        self.assertEqual(second.parameters['activation_history'][0]['previous_snapshot_ids'], [first.pk])
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(len(first.parameters['activation_history']), 1)

    def test_invalid_activation_preserves_active_version(self):
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        first = builder.activate_iprice_snapshot(snapshot=IPriceSnapshot.objects.get())
        from .iprice_models import IPriceRegionalInput
        IPriceRegionalInput.objects.all().delete()
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        with self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.activate_iprice_snapshot(snapshot=IPriceSnapshot.objects.latest('pk'))
        first.refresh_from_db()
        self.assertTrue(first.is_active)

    def test_incomplete_prices_cannot_be_activated(self):
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        IPriceSnapshotRegion.objects.update(calculated_large=None)
        with self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.activate_iprice_snapshot(snapshot=IPriceSnapshot.objects.get())
        self.assertFalse(IPriceSnapshot.objects.get().is_active)

    def test_read_api_returns_only_local_rows_and_rejects_invalid_page(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .iprice_api import SnapshotRowsView
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        user = get_user_model().objects.create_user(username='calculation-reader')
        snapshot = IPriceSnapshot.objects.get()
        for page, expected in [('1', 200), ('-1', 400), ('not-a-page', 400), ('999', 400)]:
            request = APIRequestFactory().get('/', {'page': page})
            request.organization = Organization.objects.get(code='select-market')
            force_authenticate(request, user)
            with patch('select_market.iprice_api.Dashboard.objects') as dashboards, patch('select_market.iprice_api.user_can_view_dashboard', return_value=True):
                dashboards.filter.return_value.first.return_value = object()
                response = SnapshotRowsView.as_view()(request, snapshot_id=snapshot.pk)
            self.assertEqual(response.status_code, expected)
            if expected == 200:
                self.assertEqual(response.data['count'], 1)
                self.assertEqual(response.data['rows'][0]['snapshot_product__code_1c'], '00-А')
                self.assertNotIn('calculation_details', response.data['rows'][0])

    def test_worker_completes_once_and_preserves_terminal_snapshot(self):
        from .iprice_calculation import run_calculation
        snapshot = builder.create_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        self.assertEqual(run_calculation(snapshot.pk)['status'], 'success')
        self.assertEqual(run_calculation(snapshot.pk)['status'], 'success')
        self.assertEqual(snapshot.products.count(), 1)

    def test_worker_failure_rolls_back_partial_rows(self):
        from .iprice_calculation import run_calculation
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        previous = IPriceSnapshot.objects.get()
        snapshot = builder.create_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        with patch.object(builder, 'build_iprice_snapshot_regions', side_effect=ValueError('broken region')):
            with self.assertRaises(builder.IPriceSnapshotBuildError):
                run_calculation(snapshot.pk)
        snapshot.refresh_from_db()
        previous.refresh_from_db()
        self.assertEqual(snapshot.status, 'failed')
        self.assertFalse(snapshot.products.exists())
        self.assertTrue(previous.is_current)
