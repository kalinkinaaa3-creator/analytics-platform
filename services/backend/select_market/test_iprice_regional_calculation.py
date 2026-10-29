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


class ExplanationTests(TestCase):
    def test_saved_inputs_explain_market_and_cost_methods(self):
        from types import SimpleNamespace
        from .iprice_regional_calculation import calculation_explanations
        values = dict(product_cost=Decimal('100'), logistics_unit=Decimal('10'), cost_with_logistics=Decimal('110'),
                      regional_competitor_rrp_median=Decimal('200'), base_analog=Decimal('1.1'),
                      base_exclusive=Decimal('.25'), minimum_margin=Decimal('.2'), minimum_price=Decimal('138'),
                      discount_small=Decimal('.1'), discount_medium=Decimal('.2'), discount_large=Decimal('.3'),
                      calculated_rrp=Decimal('220'))
        hints = calculation_explanations(SimpleNamespace(**values))
        self.assertIn('100,00 + 10,00 = 110,00', hints['cost_with_logistics'])
        self.assertIn('200,00 × 1,10 = 220,00', hints['preliminary_rrp'])
        self.assertIn('137,50', hints['minimum_price'])
        self.assertEqual(hints['calculated_rrp'], 'макс(220,00; 137,50 / (1 − 30,00 %)) = 220,00 ₽ → 220,00 ₽')
        self.assertNotIn('вверх до', hints['minimum_price'])
        self.assertNotIn('защита маржи', hints['calculated_rrp'])
        values['regional_competitor_rrp_median'] = None
        self.assertIn('110,00 / (1 − 25,00 %)', calculation_explanations(SimpleNamespace(**values))['preliminary_rrp'])
