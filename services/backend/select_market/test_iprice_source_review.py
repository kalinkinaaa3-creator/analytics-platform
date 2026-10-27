from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from . import iprice_domain_models as models
from .iprice_review_export import review_workbook


class SourceReviewTests(TestCase):
    def test_parser_workbook_has_all_sources_variants_and_property_columns(self):
        base = models.ParserProductUrl.objects.create(source='base', own_code='00-01', in_price=True, on_website=False)
        competitor = models.ParserProductUrl.objects.create(source='tara', status='inactive', url='https://example.test/tara')
        empty = models.ParserProductUrl.objects.create(source='tara', status='active')
        models.ParserProductClassification.objects.create(product_key=competitor.pk, status='active')
        models.ParserProductMatch.objects.create(product_key_base=base.pk, product_key_competitor=competitor.pk, status='active')
        models.BaseProductPrice.objects.create(product_key=base.pk, code_1c='00-01', name='Own', final_price=100)
        old = models.TaraProductPrice.objects.create(product_key=competitor.pk, name='Old', final_price=50)
        models.TaraProductPrice.objects.filter(pk=old.pk).update(date_add=timezone.now() - timedelta(days=2))
        for price in (100, 200):
            models.TaraProductPrice.objects.create(product_key=competitor.pk, name='New', final_price=price, properties_price=str(price))
        prop = models.ParserProductProperty.objects.create(source='tara', product_key=competitor.pk, properties='Объём', value='Old')
        models.ParserProductProperty.objects.filter(pk=prop.pk).update(date_add=timezone.now() - timedelta(days=2))
        models.ParserProductProperty.objects.create(source='tara', product_key=competitor.pk, properties='Объём', value='20 л')
        models.ParserProductProperty.objects.create(source='tara', product_key=competitor.pk, properties='Формула', value='=DANGEROUS()')
        book = load_workbook(BytesIO(review_workbook('parser_products')))
        self.assertEqual(book.sheetnames, ['ТАРА', 'ТОПАЗ', 'ПЛАСТИК СИСТЕМ', 'СЕЛЕКТ МАРКЕТ'])
        rows = list(book['ТАРА'].values)
        headers = rows[0]
        self.assertEqual(headers[:2], ('Товар классифицирован', 'Товар с найденным аналогом'))
        self.assertNotIn('Код 1С', headers)
        self.assertNotIn('В прайсе', headers)
        self.assertNotIn('На сайте', headers)
        parsed = [dict(zip(headers, row)) for row in rows[1:]]
        variants = [row for row in parsed if row['Ключ товара'] == competitor.pk]
        self.assertEqual(len(variants), 2)
        self.assertTrue(all(row['Товар классифицирован'] and row['Товар с найденным аналогом'] for row in variants))
        self.assertFalse(any(label.startswith(('Цена:', 'Свойство:')) for label in headers))
        self.assertEqual({row['Цена без НДС'] for row in variants}, {100, 200})
        self.assertTrue(all(row['Статус'] == 'Неактивен' and row['Объём'] == '20 л' for row in variants))
        self.assertEqual(book['ТАРА'].cell(2, headers.index('Формула') + 1).data_type, 's')
        self.assertTrue(any(row['Ключ товара'] == empty.pk for row in parsed))
        own_rows = list(book['СЕЛЕКТ МАРКЕТ'].values)
        own = dict(zip(own_rows[0], own_rows[1]))
        self.assertEqual(own['Код 1С'], '00-01')
        self.assertTrue(own['Товар с найденным аналогом'])
        self.assertTrue(own['В прайсе'])
        self.assertFalse(own['На сайте'])
        book.close()

    def test_health_ignores_null_zero_and_wrong_regions_and_uses_older_positive(self):
        from .iprice_models import IPricePriceImport, NomenclaturePrice
        from .iprice_health import health_report
        day = timezone.localdate()
        batch = IPricePriceImport.objects.create(date=day, rows=1)
        NomenclaturePrice.objects.create(batch=batch, date=day, code='A', shipp_region='Москва', retail=100)
        base = models.ParserProductUrl.objects.create(source='base', own_code='A')
        competitor = models.ParserProductUrl.objects.create(source='tara', prefix='moskva', url='https://example.test/item')
        models.ParserProductClassification.objects.create(product_key=competitor.pk)
        models.ParserProductMatch.objects.create(product_key_base=base.pk, product_key_competitor=competitor.pk, status='active')
        prefix = models.ParserPrefix.objects.create(source='tara', prefix='moskva', shipp_region='Москва')
        for value in (None, 0):
            models.TaraProductPrice.objects.create(product_key=competitor.pk, final_price=value)
        self.assertEqual(health_report(code='competitor_price')['count'], 1)
        self.assertIn(f' · ключ {competitor.pk}', health_report(code='competitor_price')['results'][0]['message'])
        good = models.TaraProductPrice.objects.create(product_key=competitor.pk, final_price=100)
        models.TaraProductPrice.objects.filter(pk=good.pk).update(date_add=timezone.now() - timedelta(days=1))
        self.assertEqual(health_report(code='competitor_price')['count'], 0)
        prefix.shipp_region = 'Казань'
        prefix.save()
        self.assertEqual(health_report(code='competitor_price')['count'], 1)
        prefix.shipp_region = '—'
        prefix.save()
        self.assertEqual(health_report(code='competitor_price')['count'], 0)
        models.IPriceCompetitorSelectionOverride.objects.create(product_key_base=base.pk, product_key_competitor=competitor.pk, selection_mode='exclude')
        models.TaraProductPrice.objects.all().delete()
        self.assertEqual(health_report(code='competitor_price')['count'], 0)

    def test_analog_price_queries_do_not_grow_per_product(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from .iprice_health import missing_analog_prices
        base = models.ParserProductUrl.objects.create(source='base', own_code='A')
        rows = [{'pk': 1, 'code': 'A', 'nom': 'Own', 'shipp_region': '-'}]

        def add_analog(number):
            url = models.ParserProductUrl.objects.create(source='tara', url=f'https://example.test/{number}')
            models.ParserProductClassification.objects.create(product_key=url.pk)
            models.ParserProductMatch.objects.create(product_key_base=base.pk, product_key_competitor=url.pk, status='active')

        add_analog(0)
        with CaptureQueriesContext(connection) as single:
            self.assertEqual(len(missing_analog_prices(rows, timezone.localdate())), 1)
        for number in range(1, 25):
            add_analog(number)
        with CaptureQueriesContext(connection) as multiple:
            self.assertEqual(len(missing_analog_prices(rows, timezone.localdate())), 25)
        self.assertEqual(len(multiple), len(single))
