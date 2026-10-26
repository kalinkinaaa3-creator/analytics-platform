from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from datasets.services import iprice_snapshot_builder as builder
from datasets.services.iprice_snapshot_approval import create_iprice_snapshot_approval, IPriceSnapshotApprovalError
from datasets.services.iprice_parameter_changes import apply_iprice_parameter_changes, IPriceParameterChangeError
from datasets.models import IPriceSnapshotApproval as LegacyApproval, IPriceCalculationConfig as LegacyConfig
from . import test_iprice_calculation as calculation_fixtures
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion, IPriceSnapshotApproval, IPriceParameterChangeLog
from .iprice_recovery import recover_calculation


class OperationsTests(TestCase):
    def test_comparison_filters_use_new_side_and_preserve_removed_regions(self):
        from .iprice_domain_models import IPriceSnapshotProduct
        from .iprice_filters import comparison_products, filter_options
        from datasets.services.iprice_snapshot_compare import compare_iprice_snapshots
        old_product = self.snapshot.products.get()
        old_product.group_1, old_product.is_classified = 'Old', False
        old_product.save(update_fields=['group_1', 'is_classified'])
        removed_region = IPriceSnapshotRegion.objects.create(snapshot_product=old_product, sale_region='Removed region')
        gone = IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, code_1c='GONE', nom='Removed product',
            group_1='Gone', is_classified=False, pricing_method='exclusive')
        IPriceSnapshotRegion.objects.create(snapshot_product=gone, sale_region='Region')
        newer = IPriceSnapshot.objects.create(calculation_date=self.day, version_number=2, revision_for_date=2, status='success')
        current = IPriceSnapshotProduct.objects.create(snapshot=newer, code_1c=old_product.code_1c, nom='Updated product',
            group_1='New', is_classified=True, pricing_method='exclusive')
        IPriceSnapshotRegion.objects.create(snapshot_product=current, sale_region='Region')
        added = IPriceSnapshotProduct.objects.create(snapshot=newer, code_1c='ADDED', nom='New product',
            group_1='Added', is_classified=True, pricing_method='exclusive')
        IPriceSnapshotRegion.objects.create(snapshot_product=added, sale_region='Region')
        args = dict(base_snapshot_id=self.snapshot.pk, comparison_snapshot_id=newer.pk, mode='regions', workspace=self.workspace)
        result = compare_iprice_snapshots(**args, filters={'group_1': ['Old'], 'is_classified': ['false'], 'group_4': ['__empty__']})
        self.assertEqual(result['filtered_count'], 1)
        self.assertEqual(result['results'][0]['change_type'], 'removed')
        self.assertEqual(result['results'][0]['base']['sale_region'], 'Removed region')
        selected = compare_iprice_snapshots(**args, filters={'group_1': ['New']})
        self.assertEqual(selected['filtered_count'], 1)
        self.assertEqual(selected['results'][0]['comparison']['snapshot_product_id'], current.pk)
        options = filter_options(comparison_products(base=self.snapshot, comparison=newer), {})
        self.assertEqual(set(options['group_1']), {'Old', 'New', 'Gone', 'Added'})
        dependent = filter_options(comparison_products(base=self.snapshot, comparison=newer), {'is_classified': ['false']})
        self.assertEqual(set(dependent['group_1']), {'Old', 'Gone'})
        import json
        from organizations.models import Organization
        from .iprice_api import SnapshotFiltersView
        from .iprice_operations_api import SnapshotAnalysisView
        def request(view, params):
            req = APIRequestFactory().get('/', params)
            req.organization = Organization.objects.get(code='select-market')
            force_authenticate(req, self.user)
            with patch('select_market.iprice_api.Dashboard.objects') as dashboard, patch('select_market.iprice_api.user_can_view_dashboard', return_value=True):
                dashboard.filter.return_value.first.return_value = object()
                return view.as_view()(req, snapshot_id=newer.pk)
        params = {'comparison_id': self.snapshot.pk, 'filters': json.dumps({'group_1': ['Old'], 'is_classified': ['false']})}
        response = request(SnapshotAnalysisView, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['filtered_count'], 1)
        facets = request(SnapshotFiltersView, params)
        self.assertEqual(facets.status_code, 200)
        self.assertEqual(set(facets.data['group_1']), {'Old', 'Gone'})
        self.assertEqual(request(SnapshotFiltersView, {'comparison_id': 'bad'}).status_code, 400)
        self.assertEqual(request(SnapshotFiltersView, {'comparison_id': newer.pk}).status_code, 400)
        removed_region.delete()
        options = filter_options(comparison_products(base=self.snapshot, comparison=newer), {})
        self.assertNotIn('Old', options['group_1'])

    def test_historical_routes_keep_prices_and_reject_edits(self):
        from copy import copy
        from datasets.services.iprice_snapshot_compare import _build_region_index
        from datasets.services.iprice_snapshot_export import export_iprice_snapshot_to_excel
        row = IPriceSnapshotRegion.objects.get()
        row.historical_variant = 'a' * 64
        row.save(update_fields=['historical_variant'])
        another = copy(row)
        another.pk = None
        another.historical_variant = 'b' * 64
        another.save()
        self.assertEqual(len(_build_region_index(self.snapshot)), 2)
        with self.assertRaises(IPriceParameterChangeError):
            self.parameters()
        with self.assertRaises(IPriceSnapshotApprovalError):
            create_iprice_snapshot_approval(snapshot_region=row, approved_rrp=150)
        with self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.activate_iprice_snapshot(snapshot=self.snapshot)
        stream = export_iprice_snapshot_to_excel(snapshot=self.snapshot)
        self.assertTrue(stream.read(2) == b'PK')
        stream.close()

    def test_comparison_keeps_distinct_codes_without_website(self):
        from .iprice_domain_models import IPriceSnapshotProduct
        from datasets.services.iprice_snapshot_compare import _build_region_index, _build_product_index
        for code in ('NO-SITE-1', 'NO-SITE-2'):
            product = IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, code_1c=code, nom=code,
                base_product_key=None, pricing_method='exclusive')
            IPriceSnapshotRegion.objects.create(snapshot_product=product, sale_region='Region')
        self.assertEqual(len(_build_region_index(self.snapshot)), 3)
        self.assertEqual(len(_build_product_index(self.snapshot)), 3)

    def test_readiness_does_not_require_retired_or_optional_sources(self):
        import json
        from io import StringIO
        from types import SimpleNamespace
        from datasets.management.commands.check_select_market_iprice import Command
        from .iprice_domain_models import BaseProductPrice, ParserProductClassification
        BaseProductPrice.objects.all().delete()
        ParserProductClassification.objects.all().delete()
        output = StringIO()
        with patch('datasets.management.commands.check_select_market_iprice.connection', SimpleNamespace(vendor='postgresql')), patch('datasets.management.commands.check_select_market_iprice.Dashboard.objects') as dashboards:
            dashboards.filter.return_value.exists.return_value = True
            Command(stdout=output).handle()
        report = json.loads(output.getvalue())
        self.assertTrue(report['ready_for_trial_calculation'])
        self.assertEqual(report['missing_sources'], [])
        self.assertEqual(report['purchase_rows_for_price_month'], 1)
        self.assertEqual(len(report['warnings']), 2)
        self.assertNotIn('Nomenclature', report['counts'])
        self.assertNotIn('TransportCost', report['counts'])

    def test_1c_analytics_drills_through_empty_levels_to_product(self):
        from datasets.services.iprice_price_analytics import build_iprice_price_analytics, EMPTY_GROUP_KEY, IPricePriceAnalyticsError
        product = self.snapshot.products.get()
        product.group_1, product.group_2 = 'Assortment', 'Boxes'
        product.save(update_fields=['group_1', 'group_2'])
        args = dict(snapshot=self.snapshot, filters={}, search='', page=1, page_size=50, ordering='', hierarchy='1c')
        path = {}
        for level, value in zip(('root', 'group_1', 'group_2', 'group_3'), ('Assortment', 'Boxes', EMPTY_GROUP_KEY, EMPTY_GROUP_KEY)):
            result = build_iprice_price_analytics(**args, drill_level=level, drill_path=path)
            self.assertEqual(result['results'][0]['key'], value)
            self.assertEqual(result['results'][0]['product_count'], 1)
            path = {**path, result['next_level']: value}
        leaf = build_iprice_price_analytics(**args, drill_level='group_4', drill_path=path)
        self.assertIsNone(leaf['next_level'])
        self.assertEqual(leaf['results'][0]['code_1c'], product.code_1c)
        excluded = build_iprice_price_analytics(**{**args, 'filters': {'group_1': ['Other']}}, drill_level='root', drill_path={})
        self.assertEqual(excluded['results'], [])
        from datasets.services.iprice_price_analytics import build_iprice_regional_price_analytics
        regional = build_iprice_regional_price_analytics(snapshot=self.snapshot,
            filters={'group_1': ['Assortment'], 'group_4': ['__empty__'], 'is_classified': ['true']},
            search='', drill_path={}, page=1, page_size=50)
        self.assertEqual(len(regional['results']), 1)
        with self.assertRaises(IPricePriceAnalyticsError):
            build_iprice_price_analytics(**args, drill_level='group_2', drill_path={})

    def test_delivery_edit_uses_frozen_inputs_and_keeps_source_region(self):
        from .iprice_models import IPriceRegionalInput, NomenclaturePrice
        from .iprice_regional_edits import apply
        row = IPriceSnapshotRegion.objects.get()
        code = row.snapshot_product.code_1c
        IPriceRegionalInput.objects.update(purchase_cost=999, region='REGION')
        NomenclaturePrice.objects.update(retail=999)
        apply(snapshot=self.snapshot, filters={'code_1c': [code]},
              delivery={'include_transport': False}, expected_revision=0, reason='Delivery review')
        row.refresh_from_db()
        self.assertEqual(row.product_cost, Decimal('50'))
        self.assertEqual(row.current_retail, Decimal('100'))
        self.assertEqual(row.cost_with_logistics, Decimal('50'))
        self.assertEqual(row.logistics_unit, Decimal('0'))
        self.assertEqual(IPriceRegionalInput.objects.count(), 1)
        self.assertEqual(IPriceRegionalInput.objects.get().purchase_cost, Decimal('999'))
        self.assertFalse(IPriceRegionalInput.objects.get().include_transport)
        apply(snapshot=self.snapshot, filters={'code_1c': [code]},
              delivery={'include_transport': True, 'logistics_unit': '12.34'}, expected_revision=1, reason='Delivery review')
        row.refresh_from_db()
        self.assertEqual(row.cost_with_logistics, Decimal('62.34'))

    def test_delivery_requires_value_and_rolls_back(self):
        from .iprice_regional_edits import apply
        row = IPriceSnapshotRegion.objects.get()
        row.calculation_details['regional_input']['logistics_unit'] = None
        row.save(update_fields=['calculation_details'])
        with self.assertRaises(IPriceParameterChangeError):
            apply(snapshot=self.snapshot, filters={'code_1c': [row.snapshot_product.code_1c]},
                  delivery={'include_transport': True}, expected_revision=0, reason='Delivery review')
        self.snapshot.refresh_from_db()
        self.assertEqual(self.snapshot.parameters.get('edit_revision', 0), 0)
        self.assertFalse(IPriceParameterChangeLog.objects.exists())

    def test_thousand_rows_are_paginated_without_per_row_queries(self):
        from copy import copy
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from organizations.models import Organization
        from .iprice_api import SnapshotRowsView
        original = IPriceSnapshotRegion.objects.get()
        rows = []
        for index in range(999):
            row = copy(original)
            row.pk = None
            row.sale_region = f'Region {index}'
            rows.append(row)
        IPriceSnapshotRegion.objects.bulk_create(rows)
        req = APIRequestFactory().get('/', {'page': 20})
        req.organization = Organization.objects.get(code='select-market')
        force_authenticate(req, self.user)
        with patch('select_market.iprice_api.Dashboard.objects') as dashboard, patch('select_market.iprice_api.user_can_view_dashboard', return_value=True):
            dashboard.filter.return_value.first.return_value = object()
            with CaptureQueriesContext(connection) as queries:
                response = SnapshotRowsView.as_view()(req, snapshot_id=self.snapshot.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1000)
        self.assertEqual(response.data['pages'], 20)
        self.assertEqual(len(response.data['rows']), 50)
        self.assertLessEqual(len(queries), 5)

    def setUp(self):
        calculation_fixtures.CalculationTests.setUp(self)
        self.user = get_user_model().objects.create_user(username='editor')
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        self.snapshot = IPriceSnapshot.objects.get()

    def approve(self, **kwargs):
        return create_iprice_snapshot_approval(snapshot_region=IPriceSnapshotRegion.objects.get(),
            approved_rrp=Decimal('150'), approved_by=self.user, comment='Manual decision', **kwargs)

    def parameters(self, **kwargs):
        return apply_iprice_parameter_changes(snapshot=self.snapshot, mode='regions',
            filters={'code_1c': ['00-А']}, search='', coefficient_values={'minimum_margin': '.2'},
            discount_values={'small': '.15'}, user=self.user, reason='Group review', **kwargs)

    def test_manual_price_derives_discounts_and_is_isolated(self):
        result = self.approve(expected_revision=0)
        self.assertEqual(result.approved_small, Decimal('135'))
        self.assertFalse(LegacyApproval.objects.exists())
        self.assertEqual(self.snapshot.products.get().effective_approved_rrp_median, Decimal('150'))
        self.snapshot.refresh_from_db()
        self.assertEqual(self.snapshot.parameters['edit_revision'], 1)

    def test_conflicting_manual_price_does_not_overwrite(self):
        self.approve(expected_revision=0)
        with self.assertRaises(IPriceSnapshotApprovalError):
            self.approve(expected_revision=0)
        self.assertEqual(IPriceSnapshotApproval.objects.count(), 1)

    def test_active_version_cannot_be_edited(self):
        builder.activate_iprice_snapshot(snapshot=self.snapshot, activated_by=self.user)
        with self.assertRaises(IPriceSnapshotApprovalError):
            self.approve()
        self.snapshot.refresh_from_db()
        with self.assertRaises(IPriceParameterChangeError):
            self.parameters()

    def test_deactivation_keeps_prices_and_audit_immutable_for_editors(self):
        builder.activate_iprice_snapshot(snapshot=self.snapshot, activated_by=self.user)
        result = builder.deactivate_iprice_snapshot(snapshot=self.snapshot, deactivated_by=self.user)
        self.assertFalse(result.is_active)
        self.assertTrue(result.was_active)
        self.assertEqual(result.parameters['activation_history'][-1]['action'], 'deactivate')
        with self.assertRaises(IPriceSnapshotApprovalError):
            self.approve()

    def test_parameters_recalculate_and_preserve_manual_history(self):
        original = self.approve()
        result = self.parameters(expected_revision=1)
        self.assertEqual(result['regions'], 1)
        row = IPriceSnapshotRegion.objects.get()
        self.assertEqual(row.minimum_margin, Decimal('.2'))
        approval = IPriceSnapshotApproval.objects.get()
        self.assertFalse(approval.is_current)
        self.assertEqual(approval.approved_small, Decimal('135'))
        self.assertEqual(approval.approved_at, original.approved_at)
        self.assertEqual(approval.revision, original.revision)
        self.assertIn('REAPPROVAL_REQUIRED', row.warning_codes)
        with self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.activate_iprice_snapshot(snapshot=self.snapshot)
        self.snapshot.refresh_from_db()
        self.parameters(expected_revision=self.snapshot.parameters['edit_revision'])
        row.refresh_from_db()
        self.assertIn('REAPPROVAL_REQUIRED', row.warning_codes)
        renewed = self.approve(expected_revision=1)
        self.assertEqual(renewed.revision, 2)
        self.assertEqual(renewed.approved_small, Decimal('128'))
        row.refresh_from_db()
        self.assertNotIn('REAPPROVAL_REQUIRED', row.warning_codes)
        product = self.snapshot.products.get()
        self.assertEqual(Decimal(product.calculation_details['effective_small_median']), Decimal('128'))
        from datasets.services.iprice_snapshot_export import get_effective_prices
        self.assertNotIn('distr', get_effective_prices(row))
        self.assertEqual(approval.comment, 'Manual decision')
        self.assertFalse(LegacyConfig.objects.exists())
        self.assertFalse(IPriceParameterChangeLog.objects.exclude(status='success').exists())

    def test_manual_price_below_margin_is_rejected_without_losing_approval(self):
        original = self.approve(expected_revision=0)
        with self.assertRaises(IPriceSnapshotApprovalError):
            create_iprice_snapshot_approval(snapshot_region=IPriceSnapshotRegion.objects.get(),
                approved_rrp=Decimal('60'), expected_revision=1)
        original.refresh_from_db()
        self.assertTrue(original.is_current)
        self.assertEqual(IPriceSnapshotApproval.objects.count(), 1)

    def test_activation_rechecks_margin_of_existing_prices(self):
        self.approve()
        IPriceSnapshotApproval.objects.update(approved_large=Decimal('60'))
        with self.assertRaises(builder.IPriceSnapshotBuildError):
            builder.activate_iprice_snapshot(snapshot=self.snapshot)
        self.snapshot.refresh_from_db()
        self.assertFalse(self.snapshot.is_active)

    def test_initial_market_price_does_not_depend_on_region_filter(self):
        from datasets.services.iprice_price_analytics import _product_rows, _build_regional_product_metrics
        products = self.snapshot.products.all()
        without_region = _product_rows(products)[0]
        with_region = _product_rows(products, regional_metrics=_build_regional_product_metrics(
            IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=self.snapshot)))[0]
        self.assertIsNotNone(without_region['final_rrp'])
        self.assertEqual(without_region['final_rrp'], with_region['final_rrp'])

    def test_stale_parameter_preview_is_rejected(self):
        self.approve()
        with self.assertRaises(IPriceParameterChangeError):
            self.parameters(expected_revision=0)
        self.assertEqual(IPriceSnapshotRegion.objects.get().minimum_margin, Decimal('.1'))

    def test_market_and_comparison_use_local_prices(self):
        from datasets.services.iprice_price_analytics import build_iprice_regional_price_analytics
        from datasets.services.iprice_snapshot_compare import compare_iprice_snapshots
        from .iprice_models import NomenclaturePrice
        self.approve()
        market = build_iprice_regional_price_analytics(snapshot=self.snapshot, filters={}, search='',
            drill_path={}, page=1, page_size=50)
        self.assertEqual(market['results'][0]['code_1c'], '00-А')
        self.assertEqual(market['results'][0]['final_rrp'], Decimal('150'))
        NomenclaturePrice.objects.update(retail=200)
        builder.build_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        second = IPriceSnapshot.objects.latest('pk')
        result = compare_iprice_snapshots(base_snapshot_id=self.snapshot.pk, comparison_snapshot_id=second.pk,
            mode='regions', workspace=self.workspace)
        self.assertEqual(result['results'][0]['base']['current_retail'], Decimal('100'))
        self.assertEqual(result['results'][0]['comparison']['current_retail'], Decimal('200'))

    def test_competitor_changes_invalidate_manual_price_and_keep_history(self):
        from datasets.services.iprice_competitor_selection import apply_competitor_selection
        from .iprice_domain_models import ParserProductUrl, ParserProductClassification, ParserProductMatch, TtProductPrice, IPriceCompetitorSelectionChange
        competitor = ParserProductUrl.objects.create(source='tt', url='https://example.test/competitor', status='active')
        ParserProductClassification.objects.create(product_key=competitor.pk, status='active', item_type='product')
        TtProductPrice.objects.create(product_key=competitor.pk, final_price=120)
        product = self.snapshot.products.get()
        ParserProductMatch.objects.create(product_key_base=product.base_product_key, product_key_competitor=competitor.pk, status='active', match_type='auto')
        self.approve()
        args = dict(snapshot_id=self.snapshot.pk, product_id=product.pk, competitor_product_keys=[competitor.pk],
            user=self.user, reason='Test', workspace=self.workspace)
        result = apply_competitor_selection(**args, selection_mode='include', expected_revision=1)
        self.assertEqual(result['approvals_invalidated'], 1)
        self.assertFalse(IPriceSnapshotApproval.objects.filter(is_current=True).exists())
        self.assertEqual(IPriceSnapshotApproval.objects.count(), 1)
        self.assertEqual(IPriceCompetitorSelectionChange.objects.count(), 1)
        self.assertEqual(product.competitors.get().competitor_final_price_max, Decimal('120'))

    def test_market_groups_and_zone_settings_are_local(self):
        from datasets.services.iprice_price_analytics import build_iprice_price_analytics, activate_price_zone_config, get_active_price_zone_config
        config, changed = activate_price_zone_config(below_market_threshold=Decimal('-.05'), above_market_threshold=Decimal('.05'),
            critical_threshold=Decimal('.15'), user=self.user, workspace=self.workspace)
        self.assertTrue(changed)
        self.assertEqual(get_active_price_zone_config()['above_market_threshold'], Decimal('.03'))
        result = build_iprice_price_analytics(snapshot=self.snapshot, filters={}, search='', drill_level='root',
            drill_path={}, page=1, page_size=50, ordering='')
        self.assertEqual(result['results'][0]['product_count'], 1)
        self.assertEqual(result['price_zones']['above_market_percent'], Decimal('5'))

    def test_legacy_manual_price_and_export_keep_legacy_models(self):
        from datasets.models import IPriceSnapshot as LegacySnapshot, IPriceSnapshotProduct as LegacyProduct, IPriceSnapshotRegion as LegacyRegion
        from datasets.services.iprice_snapshot_export import export_iprice_snapshot_to_excel
        from openpyxl import load_workbook
        snapshot = LegacySnapshot.objects.create(calculation_date=self.day, version_number=1,
            revision_for_date=1, status='success', is_current=True)
        product = LegacyProduct.objects.create(snapshot=snapshot, base_product_key=1, code_1c=123, nom='Legacy product', pricing_method='exclusive')
        row = LegacyRegion.objects.create(snapshot_product=product, sale_region='Legacy region', departure='Legacy plant',
            **{f'discount_{key}': Decimal('.1') for key in ('distr', 'distr_1', 'small', 'medium', 'large')})
        approval = create_iprice_snapshot_approval(snapshot_region=row, approved_rrp=Decimal('200'), approved_by=self.user)
        self.assertEqual(approval._meta.app_label, 'datasets')
        self.assertEqual(approval.approved_small, Decimal('180'))
        self.assertFalse(IPriceSnapshotApproval.objects.exists())
        book = load_workbook(export_iprice_snapshot_to_excel(snapshot=snapshot))
        cells = [cell.value for sheet in book for row in sheet for cell in row]
        self.assertIn('Legacy product', cells)
        self.assertNotIn('00-А', cells)
        book.close()

    def test_recovery_does_not_interrupt_live_worker(self):
        pending = builder.create_iprice_snapshot(calculation_date=self.day, workspace=self.workspace)
        with patch('select_market.iprice_recovery.acquire_worker_lock', side_effect=ValueError('busy')):
            with self.assertRaises(ValueError):
                recover_calculation(pending.pk, reason='restart', operator='admin')
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'building')
        with patch('select_market.iprice_recovery.acquire_worker_lock'):
            recovered = recover_calculation(pending.pk, reason='restart', operator='admin')
        self.assertEqual(recovered.status, 'failed')
        self.assertEqual(recovered.parameters['recovery']['operator'], 'admin')
        self.snapshot.refresh_from_db()
        self.assertTrue(self.snapshot.is_current)

    def test_api_validation_and_viewer_access(self):
        from .iprice_operations_api import RowApprovalView, ParameterChangeView, SnapshotHistoryView
        row = IPriceSnapshotRegion.objects.get()
        def request(view, method, data=None, edit=False, **kwargs):
            req = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
            from organizations.models import Organization
            req.organization = Organization.objects.get(code='select-market')
            force_authenticate(req, self.user)
            with patch('select_market.iprice_api.Dashboard.objects') as dashboard, patch('select_market.iprice_api.user_can_view_dashboard', return_value=True), patch('select_market.iprice_api.user_can_edit_dashboard', return_value=edit):
                dashboard.filter.return_value.first.return_value = object()
                return view.as_view()(req, snapshot_id=self.snapshot.pk, **kwargs)
        self.assertEqual(request(RowApprovalView, 'post', row_id=row.pk).status_code, 403)
        self.assertEqual(request(RowApprovalView, 'post', {'approved_rrp': 'NaN'}, edit=True, row_id=row.pk).status_code, 400)
        self.assertEqual(request(RowApprovalView, 'post', {'approved_rrp': '150', 'comment': 'reason', 'expected_revision': 0}, edit=True, row_id=row.pk).status_code, 200)
        history = request(SnapshotHistoryView, 'get')
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data['approvals']), 1)
        self.assertEqual(request(ParameterChangeView, 'post', {'filters': {'unknown': ['all']}}, edit=True).status_code, 400)
        preview = request(ParameterChangeView, 'post', {'filters': {'code_1c': ['00-А']}, 'discounts': {'small': '.2'}}, edit=True)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data['affected']['regions'], 1)
        for filters, delivery in (({'code_1c': [row.snapshot_product.code_1c]}, {'include_transport': False}),
                                  ({'sale_region': ['Region']}, {'include_transport': True, 'logistics_unit': '12.34'})):
            payload = {'filters': filters, 'delivery': delivery}
            preview = request(ParameterChangeView, 'post', payload, edit=True)
            self.assertEqual(preview.status_code, 200, preview.data)
            for invalid_reason in ('', '   ', 'x' * 2001):
                rejected = request(ParameterChangeView, 'post', {**payload, 'preview': False,
                                   'expected_revision': preview.data['edit_revision'], 'reason': invalid_reason}, edit=True)
                self.assertEqual(rejected.status_code, 400)
                self.assertIn('reason', rejected.data)
            response = request(ParameterChangeView, 'post', {**payload, 'preview': False,
                               'expected_revision': preview.data['edit_revision'], 'reason': '  Delivery review  '}, edit=True)
            self.assertEqual(response.status_code, 200, response.data)
            row.refresh_from_db()
            self.assertEqual(row.calculation_details['include_transport'], delivery['include_transport'])
        self.assertEqual(row.logistics_unit, Decimal('12.34'))
        history = request(SnapshotHistoryView, 'get')
        self.assertEqual(history.data['parameter_changes'][0]['reason'], 'Delivery review')
        self.assertEqual(request(ParameterChangeView, 'post', {'filters': {'sale_region': ['Region']}, 'delivery': {}}, edit=True).status_code, 400)
