from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from .iprice_regional_calculation import calculate_region


class RegionalCalculationTests(TestCase):
    def inputs(self, **changes):
        return SimpleNamespace(**dict(dict(purchase_cost=100, include_transport=False, logistics_unit=None,
            base_analog=1, base_exclusive='.3', minimum_margin='.1', small='.1', medium='.15', large='.2'), **changes))

    def test_delivery_is_opt_in_and_not_divided_by_truck_capacity(self):
        result = calculate_region(inputs=self.inputs(logistics_unit='12.34'))
        self.assertEqual(result['cost_with_logistics'], 100)
        self.assertEqual(result['logistics_unit'], 0)
        result = calculate_region(inputs=self.inputs(include_transport=True, logistics_unit='12.34'))
        self.assertEqual(result['cost_with_logistics'], Decimal('112.34'))
        self.assertEqual(result['prices_net']['retail'], 160)
        self.assertEqual(result['prices_gross']['retail'], 195)
        self.assertEqual(set(result['prices_net']), {'retail', 'small', 'medium', 'large'})

    def test_missing_purchase_or_enabled_delivery_never_produces_prices(self):
        for values in (dict(purchase_cost=None), dict(include_transport=True), dict(logistics_unit='NaN', include_transport=True)):
            result = calculate_region(inputs=self.inputs(**values))
            self.assertTrue(result['error_codes'])
            self.assertFalse(result['prices_net'])

    def test_unclassified_product_can_use_exclusive_formula(self):
        result = calculate_region(inputs=self.inputs(base_analog=None))
        self.assertEqual(result['prices_net']['retail'], 143)
        self.assertFalse(result['error_codes'])

    def test_market_formula_uses_net_purchase_floor_and_actual_discounts(self):
        result = calculate_region(inputs=self.inputs(), market_prices=[10, 0, None])
        self.assertEqual(result['market_median'], 10)
        self.assertEqual(result['prices_net']['retail'], 140)
        self.assertEqual(result['prices_net']['large'], 112)
        for price in result['prices_net'].values():
            self.assertGreaterEqual(price * Decimal('.9'), result['cost_with_logistics'])

    def test_rounding_preserves_margin_across_discounts(self):
        for cost in ('1', '100', '112.34'):
            for discount in ('0', '.2', '.500001', '.999999'):
                result = calculate_region(inputs=self.inputs(purchase_cost=cost, large=discount), market_prices=[1])
                self.assertFalse(result['error_codes'])
                for price in result['prices_net'].values():
                    self.assertGreaterEqual(price * Decimal('.9'), Decimal(cost))
