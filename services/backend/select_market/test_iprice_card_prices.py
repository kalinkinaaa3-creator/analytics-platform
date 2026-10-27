from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .iprice_card_prices import regional_card_prices
from .iprice_regional_calculation import competitor_matches_region


class CardPricesTests(SimpleTestCase):
    def test_medians_are_computed_per_region_before_card_summary(self):
        card = regional_card_prices({'regional_entries': [
            {'region': 'Москва', 'price': '100', 'url': 'https://example.test/1'},
            {'region': 'Москва', 'price': '200', 'url': 'https://example.test/2'},
            {'region': 'Москва', 'price': '300', 'url': 'https://example.test/3'},
            {'region': 'СПБ', 'price': '800', 'url': 'https://example.test/4'},
            {'region': 'СПБ', 'price': None},
        ]})
        self.assertEqual(card['price'], Decimal('500'))
        self.assertEqual([row['price'] for row in card['regional_entries']], [200, 800])
        self.assertEqual(len(card['regional_entries'][0]['urls']), 3)

    def test_market_variants_and_missing_prices(self):
        card = regional_card_prices({'variants': [
            {'regions': ['Москва'], 'price': '10'},
            {'regions': ['СПБ'], 'price': '30'},
            {'regions': ['СПБ'], 'price': 'NaN'},
        ]})
        self.assertEqual(card['price'], 20)
        self.assertEqual(regional_card_prices({'variants': [{'price': None}]})['price'], None)

    def test_matching_regions_and_explicit_universal_dash(self):
        competitor = SimpleNamespace(is_all_regions=False, applicable_regions=['Москва'])
        self.assertTrue(competitor_matches_region(competitor, ' Москва '))
        self.assertFalse(competitor_matches_region(competitor, 'СПБ'))
        self.assertFalse(competitor_matches_region(competitor, ''))
        for dash in ('-', '—', '–'):
            self.assertTrue(competitor_matches_region(competitor, dash))
            universal = SimpleNamespace(is_all_regions=False, applicable_regions=[dash])
            self.assertTrue(competitor_matches_region(universal, 'СПБ'))
