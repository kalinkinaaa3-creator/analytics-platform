from datetime import date
from decimal import Decimal

from django.test import TestCase

from . import test_iprice_ui_api as ui_api_tests
from .iprice_api import SnapshotRowsView, SnapshotFiltersView, HealthView
from .iprice_operations_api import SnapshotAnalysisView, OwnAssortmentView
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotProduct, IPriceSnapshotRegion


class ListControlsTests(TestCase):
    request = ui_api_tests.UIAPITests.request

    def setUp(self):
        ui_api_tests.UIAPITests.setUp(self)
        self.snapshot = IPriceSnapshot.objects.create(calculation_date=date(2026, 10, 1), version_number=1, revision_for_date=1, status='success')
        self.product = IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, code_1c='00-A', nom='Box', pricing_method='exclusive', category='C', subcategory='S', subcategory_type='T', item_type='item')

    def row(self, price, region, **kwargs):
        return IPriceSnapshotRegion.objects.create(snapshot_product=self.product, sale_region=region, current_retail=price, default_approved_rrp=price, regional_competitor_rrp_median=100, **kwargs)

    def get(self, view=SnapshotRowsView, **params):
        return self.request(view, 'get', data=params, snapshot_id=self.snapshot.pk)

    def test_zone_boundaries_and_no_market(self):
        for value in (96, 97, 103, 104, 110, 111):
            self.row(value, str(value))
        self.row(None, 'missing')
        for zone, expected in [('below_market', [96]), ('in_market', [97, 103]), ('above_market', [104, 110]), ('critical_above', [111]), ('no_market_data', [None])]:
            with self.subTest(zone=zone):
                result = self.get(zone=zone)
                self.assertEqual(result.status_code, 200)
                self.assertEqual([r['current_retail'] for r in result.data['rows']], expected)
        self.assertEqual(self.get(zone='invalid').status_code, 400)
        self.assertEqual(self.get(mode='invalid').status_code, 400)

    def test_filtering_and_grouping_precede_pagination(self):
        for i in range(52):
            self.row(100, str(i), calculation_status='success')
        self.row(120, 'target', calculation_status='warning', warning_codes=['MISSING_CLASSIFICATION'])
        self.product.current_retail_median = 120
        self.product.effective_approved_rrp_median = 120
        self.product.competitor_rrp_median = 100
        self.product.save()
        result = self.get(problems_only='true', search='00-A')
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(result.data['rows'][0]['sale_region'], 'target')
        grouped = self.get(mode='products')
        self.assertEqual(grouped.data['count'], 1)
        self.assertEqual(len(grouped.data['rows'][0]['regions']), 53)
        self.assertEqual(len(self.get(zone='critical_above', mode='products').data['rows'][0]['regions']), 53)
        self.assertEqual(grouped.data['rows'][0]['summary']['current_retail_median'], 120)
        self.assertEqual(self.get(mode='products', page=2).status_code, 400)

    def test_analysis_uses_shared_zone_filter(self):
        self.row(90, 'below')
        self.row(120, 'above')
        result = self.get(SnapshotAnalysisView, zone='below_market')
        self.assertEqual(result.status_code, 200)
        self.assertEqual([r['sale_region'] for r in result.data['results']], ['below'])

    def test_own_assortment_uses_select_market_storage(self):
        from datasets.models import IPriceSnapshotProduct as LegacyProduct
        other = IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, code_1c='00-B', nom='Second', pricing_method='exclusive', category='C', subcategory='S', subcategory_type='T', item_type='item')
        IPriceSnapshotRegion.objects.create(snapshot_product=other, sale_region='R', current_retail=Decimal('123'))
        self.assertEqual(LegacyProduct.objects.count(), 0)
        result = self.request(OwnAssortmentView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk)
        self.assertEqual(result.status_code, 200)
        self.assertEqual([r['code_1c'] for r in result.data['results']], ['00-B'])
        self.assertEqual(result.data['results'][0]['price'], 123)

    def test_own_cards_show_medians_and_one_row_per_region(self):
        other = IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, code_1c='00-B', nom='Second',
            pricing_method='exclusive', category='C', subcategory='S', subcategory_type='T', item_type='item')
        for region, price in [('North', 100), ('South', 200), ('West', 1000)]:
            IPriceSnapshotRegion.objects.create(snapshot_product=other, sale_region=region,
                current_retail=price, default_approved_rrp=price)
        result = self.request(OwnAssortmentView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk)
        card = result.data['results'][0]
        self.assertEqual(card['final_price'], 200)
        self.assertEqual(card['price'], 200)
        self.assertEqual([row['final_price'] for row in card['regional_prices']], [100, 200, 1000])

    def test_health_missing_data_is_not_success(self):
        self.row(100, 'R', error_codes=['MISSING_PRODUCT_COST', 'MISSING_PRODUCT_COST'])
        response = self.request(HealthView, 'get')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['price_date'])
        self.assertEqual(response.data['issues'], [{'code': 'MISSING_PRODUCT_COST', 'count': 1, 'severity': 'error'}])
        self.assertEqual(self.request(HealthView, 'get', view_allowed=False).status_code, 403)

    def test_market_assortment_isolated_and_legacy_default_preserved(self):
        from datasets.services.iprice_market_assortment import build_iprice_market_assortment
        from datasets.services.iprice_workspace import IPriceWorkspace
        from .iprice_domain_models import ParserProductUrl, ParserProductClassification
        from datasets.models import ParserProductUrl as LegacyURL, ParserProductClassification as LegacyClass
        fields = dict(category='C', subcategory='S', subcategory_type='T', item_type='item')
        local = ParserProductUrl.objects.create(source='tt', url='https://example.test/local', status='active')
        legacy = LegacyURL.objects.create(source='tt', url='https://example.test/legacy', status='active')
        ParserProductClassification.objects.create(product_key=local.pk, **fields)
        LegacyClass.objects.create(product_key=legacy.pk, **fields)
        result = build_iprice_market_assortment(snapshot_product=self.product, workspace=IPriceWorkspace('select-market'))
        self.assertEqual([r['url'] for r in result['results']], [local.url])
        result = build_iprice_market_assortment(snapshot_product=self.product)
        self.assertEqual([r['url'] for r in result['results']], [legacy.url])

    def test_health_matches_purchase_by_code_region_and_month(self):
        from .iprice_models import IPricePriceImport, NomenclaturePrice, IPriceRegionalInput
        batch = IPricePriceImport.objects.create(date=date(2026, 10, 1), rows=3)
        for code in ('A', 'B', 'C'):
            NomenclaturePrice.objects.create(batch=batch, date=batch.date, code=code, shipp_region='R', retail=100)
        IPriceRegionalInput.objects.create(code='A', region='r', month=batch.date, purchase_cost=10, include_transport=True, logistics_unit=0)
        IPriceRegionalInput.objects.create(code='B', region='R', month=batch.date, purchase_cost=10, include_transport=True)
        IPriceRegionalInput.objects.create(code='C', region='other', month=batch.date, purchase_cost=10)
        response = self.request(HealthView, 'get')
        self.assertEqual({r['key']: r['count'] for r in response.data['source_checks']}, {'purchase': 1, 'delivery': 1, 'retail': 0})

    def test_facets_follow_zone_and_problem_controls(self):
        self.product.group_1 = 'Below'
        self.product.current_retail_median = 90
        self.product.effective_approved_rrp_median = 90
        self.product.competitor_rrp_median = 100
        self.product.save()
        self.row(90, 'R', calculation_status='success')
        other = IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, code_1c='B', nom='B', group_1='Above', pricing_method='exclusive', current_retail_median=120, effective_approved_rrp_median=120, competitor_rrp_median=100)
        IPriceSnapshotRegion.objects.create(snapshot_product=other, sale_region='R', current_retail=120, default_approved_rrp=120, regional_competitor_rrp_median=100, calculation_status='warning', warning_codes=['WARNING'])
        self.assertEqual(self.get(SnapshotFiltersView, zone='below_market').data['group_1'], ['Below'])
        self.assertEqual(self.get(SnapshotFiltersView, problems_only='true').data['group_1'], ['Above'])
        self.assertEqual(self.get(SnapshotFiltersView, mode='products', zone='critical_above').data['group_1'], ['Above'])

    def test_used_competitor_requires_valid_price_and_applicable_region(self):
        from .iprice_domain_models import IPriceSnapshotCompetitor
        from datasets.services.iprice_market_assortment import get_used_competitor_keys
        self.row(100, 'R')
        for key, state, price, regions in [(1, 'error', None, ['R']), (2, 'success', 100, ['OTHER']), (3, 'success', 100, ['R'])]:
            IPriceSnapshotCompetitor.objects.create(snapshot_product=self.product, competitor_product_key=key, source='tt', calculation_status=state, competitor_final_price_max=price, applicable_regions=regions)
        self.assertEqual(get_used_competitor_keys(snapshot_product=self.product), {3})

    def test_zone_uses_final_price_including_manual_approval(self):
        from .iprice_domain_models import IPriceSnapshotApproval
        row = self.row(90, 'R')
        row.default_approved_rrp = 120
        row.save()
        self.assertEqual(self.get(zone='critical_above').data['count'], 1)
        self.assertEqual(self.get(zone='below_market').data['count'], 0)
        IPriceSnapshotApproval.objects.create(snapshot_region=row, revision=1, approved_rrp=100, is_current=True)
        result = self.get(zone='in_market')
        self.assertEqual(result.data['rows'][0]['zone'], 'in_market')
        result = self.get(SnapshotAnalysisView, zone='in_market')
        self.assertEqual([r['sale_region'] for r in result.data['results']], ['R'])

    def test_parameter_scope_matches_rows_before_pagination(self):
        from .iprice_regional_edits import resolve
        self.row(120, 'target', calculation_status='warning')
        for i in range(51):
            self.row(90, str(i), calculation_status='success')
        scope = {'mode': 'regions', 'zone': 'critical_above', 'problems_only': True}
        displayed = self.get(search='00-A', **scope)
        affected = resolve(self.snapshot, {}, search='00-A', list_scope=scope)
        self.assertEqual(list(affected.values_list('pk', flat=True)), [r['id'] for r in displayed.data['rows']])
        self.assertEqual(resolve(self.snapshot, {}, list_scope={**scope, 'zone': '', 'problems_only': False}).count(), 52)

    def test_multiple_zones_and_sorting(self):
        self.row(90, 'A')
        self.row(120, 'B')
        self.row(100, 'C')
        result = self.get(zone='below_market,critical_above', ordering='-final')
        self.assertEqual([r['effective']['rrp'] for r in result.data['rows']], [120, 90])
        self.assertEqual(self.get(ordering='unsupported').status_code, 400)

    def test_deviation_and_margin_sorting(self):
        self.row(90, 'A', cost_with_logistics=45)
        self.row(120, 'B', cost_with_logistics=96)
        self.row(100, 'C', cost_with_logistics=60)
        for ordering, expected in [('deviation', ['A', 'C', 'B']), ('-margin', ['A', 'C', 'B'])]:
            response = self.get(ordering=ordering)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['sale_region'] for row in response.data['rows']], expected)
        self.assertEqual(self.get(mode='products', ordering='deviation').status_code, 200)
        self.assertEqual(self.get(mode='products', ordering='margin').status_code, 400)

    def test_region_method_and_status_filters_share_bulk_scope(self):
        import json
        from .iprice_regional_edits import resolve
        self.product.calculation_status = 'warning'
        self.product.save()
        selected = self.row(100, 'North')
        self.row(110, 'South')
        filters = {'sale_region': ['North'], 'pricing_method': ['exclusive'], 'calculation_status': ['warning']}
        response = self.get(filters=json.dumps(filters))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['rows']], [selected.pk])
        self.assertEqual(list(resolve(self.snapshot, filters).values_list('pk', flat=True)), [selected.pk])
        options = self.get(SnapshotFiltersView, filters=json.dumps(filters))
        self.assertEqual(options.data['sale_region'], ['North', 'South'])
        self.assertEqual(self.get(filters=json.dumps({'pricing_method': ['analog']})).data['count'], 0)

    def test_row_history_is_scoped_to_snapshot(self):
        from .iprice_operations_api import SnapshotHistoryView
        row = self.row(100, 'North')
        response = self.request(SnapshotHistoryView, 'get', snapshot_id=self.snapshot.pk, data={'row_id': row.pk})
        self.assertEqual(response.status_code, 200)
        other = IPriceSnapshot.objects.create(calculation_date=date(2026, 10, 2), version_number=2, revision_for_date=1)
        response = self.request(SnapshotHistoryView, 'get', snapshot_id=other.pk, data={'row_id': row.pk})
        self.assertEqual(response.status_code, 404)

    def test_market_region_groups_aggregate_before_pagination(self):
        self.row(90, 'North')
        self.row(110, 'South')
        response = self.request(SnapshotAnalysisView, 'get', snapshot_id=self.snapshot.pk,
            data={'view': 'region_groups', 'ordering': 'median_deviation_percent'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['key'] for row in response.data['results']], ['North', 'South'])
        self.assertEqual(response.data['results'][0]['product_count'], 1)
        self.assertEqual(response.data['results'][0]['market_coverage_percent'], 100)
        self.assertEqual(response.data['summary']['total_products'], 1)
        self.assertEqual(response.data['summary']['median_final_rrp'], 100)

    def test_market_summary_obeys_zone_and_accepts_product_sort(self):
        self.product.effective_approved_rrp_median = 120
        self.product.competitor_rrp_median = 100
        self.product.save()
        response = self.request(SnapshotAnalysisView, 'get', snapshot_id=self.snapshot.pk,
            data={'view': 'groups', 'hierarchy': 'classification', 'zone': 'below_market', 'ordering': '-median_final_rrp'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_products'], 0)
        self.assertEqual(response.data['results'], [])

    def test_parameter_history_is_limited_and_scoped_to_frozen_rows(self):
        from .iprice_domain_models import IPriceParameterChangeLog
        from .iprice_operations_api import SnapshotHistoryView
        selected, other = self.row(100, 'North'), self.row(110, 'South')
        for number in range(55):
            IPriceParameterChangeLog.objects.create(snapshot_id=self.snapshot.pk, mode='regions',
                changes={'base_analog': '1.1'}, affected={'row_ids': [selected.pk]}, reason=str(number))
        IPriceParameterChangeLog.objects.create(snapshot_id=self.snapshot.pk, mode='regions',
            changes={'base_analog': '1.2'}, affected={'row_ids': [other.pk]}, reason='Other region')
        response = self.get(SnapshotHistoryView, parameter_row_id=selected.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['parameter_changes']), 50)
        self.assertEqual(response.data['parameter_changes'][0]['reason'], '54')
        self.assertNotIn('Other region', [item['reason'] for item in response.data['parameter_changes']])

    def test_rows_page_size_is_bounded_and_does_not_truncate_product_regions(self):
        for index in range(26):
            self.row(100, str(index))
        first = self.get(page_size=25)
        self.assertEqual(len(first.data['rows']), 25)
        self.assertEqual(first.data['pages'], 2)
        self.assertEqual(len(self.get(page_size=25, page=2).data['rows']), 1)
        self.assertEqual(len(self.get(page_size=25, mode='products').data['rows'][0]['regions']), 26)
        self.assertEqual(self.get(page_size=1000).status_code, 400)

    def test_legacy_market_semantics_are_preserved(self):
        from datasets.models import IPriceSnapshot as LegacySnapshot, IPriceSnapshotProduct as LegacyProduct
        from datasets.services.iprice_price_analytics import _product_rows
        legacy = LegacySnapshot.objects.create(calculation_date=self.snapshot.calculation_date, version_number=1, revision_for_date=1)
        LegacyProduct.objects.create(snapshot=legacy, base_product_key=1, code_1c=1, pricing_method='analog',
            current_retail_median=90, effective_approved_rrp_median=120, competitor_rrp_median=100)
        self.product.current_retail_median = 90
        self.product.effective_approved_rrp_median = 120
        self.product.competitor_rrp_median = 100
        self.product.save()
        self.assertEqual(_product_rows(LegacyProduct.objects.all())[0]['deviation'], Decimal('-0.1'))
        self.assertEqual(_product_rows(IPriceSnapshotProduct.objects.all())[0]['deviation'], Decimal('0.2'))

    def test_manual_price_preview_rounding_and_margin_without_writes(self):
        from .iprice_operations_api import RowApprovalView
        from .iprice_domain_models import IPriceSnapshotApproval
        row = self.row(100, 'R', cost_with_logistics=80, minimum_margin=Decimal('.2'), discount_small=Decimal('.1'), discount_medium=Decimal('.15'), discount_large=Decimal('.2'))
        def preview(price):
            return self.request(RowApprovalView, 'get', snapshot_id=self.snapshot.pk, row_id=row.pk, data={'price': price})
        response = preview('125')
        self.assertTrue(response.data['valid'])
        self.assertEqual(response.data['prices']['small'], 113)
        self.assertEqual(response.data['gross']['rrp'], 153)
        self.assertFalse(preview('124').data['valid'])
        self.assertEqual(preview('125.5').status_code, 400)
        self.assertFalse(IPriceSnapshotApproval.objects.exists())

    def test_health_details_filter_and_review_workbooks(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from .iprice_api import ReviewExportView
        self.row(100, 'R', error_codes=['MISSING_PRODUCT_COST'], warning_codes=['MISSING_CLASSIFICATION'])
        response = self.request(HealthView, 'get', data={'level': 'error', 'search': '00-A'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['code'], 'MISSING_PRODUCT_COST')
        self.assertEqual(self.request(ReviewExportView, 'get', kind='parser_products', view_allowed=False).status_code, 403)
        for kind in ['parser_products', 'preparation_check']:
            response = self.request(ReviewExportView, 'get', kind=kind)
            self.assertEqual(response.status_code, 200)
            with BytesIO(response.content) as stream:
                book = load_workbook(stream, read_only=True)
                self.assertGreater(len(book.sheetnames), 1)
                if kind == 'preparation_check':
                    self.assertTrue({'Действующая классификация', 'Действующие аналоги',
                                     'Действующие префиксы', 'Настройки расчёта',
                                     'Последние закупочные цены'}.issubset(book.sheetnames))
                    self.assertEqual(next(book['Последние закупочные цены'].values),
                                     ('Дата', 'Наименование', 'Регион', 'Закупочная цена без НДС, руб.', 'Код 1С'))
                book.close()

    def test_review_exports_latest_purchase_file_and_active_classification(self):
        from io import BytesIO
        from openpyxl import Workbook, load_workbook
        from .iprice_models import IPriceSourceImport
        from .iprice_domain_models import ParserProductClassification, ParserProductUrl, ParserProductMatch
        from .iprice_review_export import review_workbook
        for code in ['OLD', '=TEXT-CODE']:
            source = Workbook()
            source.active.append(['date', 'code', 'name', 'region', 'cost'])
            source.active.append(['2026-10-01', code, 'Name', 'Region', 123])
            stream = BytesIO()
            source.save(stream)
            source.close()
            IPriceSourceImport.objects.create(kind='product_cost', filename='cost.xlsx', checksum=code, content=stream.getvalue())
        ParserProductUrl.objects.create(pk=900, source='base', own_code='00-OUR', url='https://example.test/own')
        ParserProductClassification.objects.create(product_key=900, status='active', category='Active')
        ParserProductMatch.objects.create(product_key_base=900, product_key_competitor=123, status='active')
        ParserProductClassification.objects.create(product_key=901, status='inactive', category='Inactive')
        book = load_workbook(BytesIO(review_workbook('preparation_check')))
        self.assertEqual(book['Последние закупочные цены'].max_row, 2)
        self.assertEqual(book['Последние закупочные цены']['E2'].value, '=TEXT-CODE')
        self.assertEqual(book['Последние закупочные цены']['E2'].data_type, 's')
        self.assertEqual(list(book['Действующая классификация'].values)[1][1], 'Active')
        self.assertEqual(book['Действующая классификация'].max_row, 2)
        self.assertEqual(list(book['Действующая классификация'].values)[0][-1], 'Код 1С')
        self.assertEqual(list(book['Действующая классификация'].values)[1][-1], '00-OUR')
        self.assertEqual(list(book['Действующие аналоги'].values)[1][-1], '00-OUR')
        book.close()

    def test_product_details_and_snapshot_counts(self):
        from .iprice_api import SnapshotListView
        from .iprice_operations_api import ProductDetailsView
        from .iprice_domain_models import IPriceSnapshotCompetitor
        self.row(100, 'R', calculation_status='error')
        IPriceSnapshotCompetitor.objects.create(snapshot_product=self.product, competitor_product_key=123, source='tt',
            competitor_final_price_max=90, applicable_regions=['R'], price_variants=[{'name': 'Competitor', 'image': 'https://example.test/image.png'}])
        response = self.request(ProductDetailsView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['competitor_cards'][0]['name'], 'Competitor')
        self.assertTrue(response.data['competitor_cards'][0]['is_used_in_snapshot'])
        summary = self.request(SnapshotListView, 'get').data[0]
        self.assertEqual((summary['products_count'], summary['regions_count'], summary['errors_count']), (1, 1, 1))

    def test_comparison_accepts_product_mode_and_change_type(self):
        base = IPriceSnapshot.objects.create(calculation_date=date(2026, 9, 1), version_number=2, revision_for_date=1, status='success')
        IPriceSnapshotProduct.objects.create(snapshot=base, code_1c='OLD', nom='Old', pricing_method='exclusive')
        response = self.get(SnapshotAnalysisView, comparison_id=base.pk, mode='products', change_type='removed')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'products')
        self.assertEqual([item['base']['code_1c'] for item in response.data['results']], ['OLD'])

    def test_parameter_apply_rejects_scope_changed_by_zone_configuration(self):
        from .iprice_operations_api import ParameterChangeView
        from .iprice_domain_models import IPricePriceZoneConfig, IPriceParameterChangeLog
        self.row(120, 'R')
        payload = {'filters': {}, 'list_scope': {'mode': 'regions', 'zone': 'critical_above'},
                   'coefficients': {'base_analog': '1.1'}, 'preview': True}
        response = self.request(ParameterChangeView, 'post', snapshot_id=self.snapshot.pk, data=payload, edit_allowed=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['affected']['regions'], 1)
        payload.update(preview=False, reason='Review', expected_revision=response.data['edit_revision'], expected_scope=response.data['affected']['scope_signature'])
        IPricePriceZoneConfig.objects.create(above_market_threshold=Decimal('.5'), critical_threshold=Decimal('1'))
        response = self.request(ParameterChangeView, 'post', snapshot_id=self.snapshot.pk, data=payload, edit_allowed=True)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(IPriceParameterChangeLog.objects.exists())
