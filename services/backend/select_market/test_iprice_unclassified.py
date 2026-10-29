from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from . import iprice_domain_models as m
from . import test_iprice_ui_api as ui
from .iprice_classification_api import UnclassifiedView
from .iprice_unclassified import catalogue, classify
from .test_iprice_sources import excel
from .iprice_sources import import_source


class UnclassifiedTests(TestCase):
    request = ui.UIAPITests.request

    def setUp(self):
        ui.UIAPITests.setUp(self)
        self.snapshot = m.IPriceSnapshot.objects.create(calculation_date=timezone.localdate(), version_number=1, revision_for_date=1, status='success')
        self.base = m.ParserProductUrl.objects.create(source='base', own_code='001', status='active')
        self.product = m.IPriceSnapshotProduct.objects.create(snapshot=self.snapshot, base_product_key=self.base.pk, code_1c='001', nom='Bucket')
        self.values = dict(category='Type', subcategory='Category', subcategory_type='Subcategory', color='blue', material='PP', modification='', article_number_analogs='G', item_type='product')
        m.ParserProductClassification.objects.create(product_key=self.base.pk, **self.values)
        self.urls = []
        for prefix, region in [('msk', 'Москва'), ('kzn', 'Казань')]:
            m.ParserPrefix.objects.create(source='tara', prefix=prefix, shipp_region=region)
            self.urls.append(m.ParserProductUrl.objects.create(source='tara', prefix=prefix, url=f'https://{prefix}.tara.test/catalog/bucket', status='active'))
        for price in (100, 200):
            m.TaraProductPrice.objects.create(product_key=self.urls[0].pk, name='Ведро', final_price=price)
        m.TaraProductPrice.objects.create(product_key=self.urls[1].pk, name='Ведро', final_price=300)
        old = m.TaraProductPrice.objects.create(product_key=self.urls[1].pk, name='Old', final_price=9999)
        m.TaraProductPrice.objects.filter(pk=old.pk).update(date_add=timezone.now() - timedelta(days=5))

    def payload(self):
        card = next(card for card in catalogue()['results'] if self.urls[0].pk in card['product_keys'])
        return dict(product_keys=card['product_keys'], revision=card['revision'], values=self.values, reason='Reviewed')

    def test_regions_median_search_and_empty_price(self):
        data = catalogue(search='ВЕДРО')
        self.assertEqual(data['count'], 1)
        card = data['results'][0]
        self.assertEqual(card['price'], Decimal('225'))
        self.assertEqual(len(card['regional_entries']), 2)
        self.assertEqual(len(card['dates']), 1)
        self.assertEqual(catalogue(search='kzn.tara')['results'][0]['product_keys'], card['product_keys'])
        self.assertEqual(catalogue(source='ps')['count'], 0)
        m.TaraProductPrice.objects.all().update(final_price=0)
        self.assertIsNone(catalogue()['results'][0]['price'])
        empty = m.ParserProductUrl.objects.create(source='tt', url='https://tt.test/new')
        self.assertIsNone(catalogue(search='/new')['results'][0]['price'])
        self.assertEqual(catalogue(search='/new')['results'][0]['product_keys'], [empty.pk])

    def test_save_permission_history_stale_and_snapshot_unchanged(self):
        payload = self.payload()
        kwargs = dict(snapshot_id=self.snapshot.pk, product_id=self.product.pk, data=payload)
        self.assertEqual(self.request(UnclassifiedView, 'post', **kwargs).status_code, 403)
        response = self.request(UnclassifiedView, 'post', edit_allowed=True, **kwargs)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(m.ParserProductClassification.objects.filter(manual_edit=True).count(), 2)
        self.assertEqual(m.ParserProductMatch.objects.filter(status='active', match_type='auto').count(), 2)
        self.assertEqual(m.ClassificationChange.objects.get().after, self.values)
        self.assertEqual(catalogue()['count'], 0)
        self.assertEqual(self.request(UnclassifiedView, 'post', edit_allowed=True, **kwargs).status_code, 400)
        self.product.refresh_from_db()
        self.assertFalse(self.product.category)
        self.assertEqual(self.request(UnclassifiedView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk, view_allowed=False).status_code, 403)

    def test_export_includes_ui_and_excel_and_import_replaces_ui(self):
        payload = self.payload()
        classify(keys=payload['product_keys'], revision=payload['revision'], values=self.values, reason='Reviewed', user=self.user, organization=self.org)
        row = [self.base.pk, 'Type', 'Category', 'Subcategory', 'blue', 'PP', '', 'G', 'product']
        def load(*rows):
            return import_source(excel('product_classification', *rows), kind='product_classification', filename='class.xlsx', user=self.user, organization=self.org)
        from io import BytesIO
        from openpyxl import load_workbook
        from .iprice_review_export import review_workbook
        book = load_workbook(BytesIO(review_workbook('preparation_check')))
        rows = list(book['Действующая классификация'].values)
        exported = [dict(zip(rows[0], row)) for row in rows[1:]]
        self.assertEqual(len(exported), 3)
        self.assertEqual({row['Источник классификации'] for row in exported}, {'Интерфейс', 'Загрузка Excel'})
        book.close()
        load(row, [self.urls[0].pk, 'Changed', *row[2:]])
        self.assertEqual(m.ParserProductClassification.objects.get(product_key=self.urls[0].pk).category, 'Changed')
        self.assertFalse(m.ParserProductClassification.objects.get(product_key=self.urls[0].pk).manual_edit)
        load(row)
        self.assertEqual(m.ParserProductClassification.objects.filter(status='active').count(), 1)
        self.assertEqual(m.ParserProductMatch.objects.filter(status='active').count(), 0)
        self.assertEqual(m.ClassificationChange.objects.count(), 1)

    def test_variants_are_not_merged_and_deleted_group_is_stale(self):
        m.ParserProductUrl.objects.create(source='tara', prefix='msk', url=self.urls[0].url, additional_property='other')
        self.assertEqual(catalogue()['count'], 2)
        payload = self.payload()
        self.urls[0].status = 'inactive'
        self.urls[0].save()
        with self.assertRaises(ValueError):
            classify(keys=payload['product_keys'], revision=payload['revision'], values=self.values, reason='Reviewed', user=self.user, organization=self.org)

    def test_only_uploaded_combinations_are_allowed_and_page_size_validated(self):
        extra = dict(self.values, material='Metal')
        other = m.ParserProductUrl.objects.create(source='base', own_code='002')
        m.ParserProductClassification.objects.create(product_key=other.pk, manual_edit=True, **extra)
        response = self.request(UnclassifiedView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk)
        self.assertEqual(response.data['combinations'], [self.values])
        for values in (extra, dict(self.values, category='Unknown')):
            payload = dict(self.payload(), values=values)
            response = self.request(UnclassifiedView, 'post', snapshot_id=self.snapshot.pk, product_id=self.product.pk,
                                    edit_allowed=True, data=payload)
            self.assertEqual(response.status_code, 400, response.data)
        for size in ('oops', 24, 101):
            response = self.request(UnclassifiedView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk,
                                    data={'page_size': size})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(m.ClassificationChange.objects.count(), 0)

    def test_classified_analog_is_visible_without_changing_saved_calculation(self):
        from .iprice_operations_api import ProductDetailsView, OwnAssortmentView
        for key, value in self.values.items():
            setattr(self.product, key, value)
        self.product.save()
        payload = self.payload()
        classify(keys=payload['product_keys'], revision=payload['revision'], values=self.values,
                 reason='Reviewed', user=self.user, organization=self.org)
        response = self.request(ProductDetailsView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['competitor_cards']), 1)
        card = response.data['competitor_cards'][0]
        self.assertTrue(card['is_current_analog'])
        self.assertFalse(card['is_used_in_snapshot'])
        self.assertEqual(self.product.competitors.count(), 0)
        market = self.request(OwnAssortmentView, 'get', snapshot_id=self.snapshot.pk, product_id=self.product.pk, kind='market')
        self.assertEqual(market.data['counts']['cards'], 1)
