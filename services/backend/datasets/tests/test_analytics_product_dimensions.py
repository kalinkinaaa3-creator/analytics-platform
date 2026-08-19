from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from datasets.services.parsers.analytics_product_processor import (
    _condition_matches,
)


class CompoundDimensionConditionTests(SimpleTestCase):
    def setUp(self):
        self.runtime = SimpleNamespace(
            metrics={
                "length": SimpleNamespace(tolerance=Decimal("9")),
                "width": SimpleNamespace(tolerance=Decimal("9")),
                "height": SimpleNamespace(tolerance=Decimal("10")),
            },
            property_rules={},
        )

    def test_different_second_dimension_does_not_fall_back_to_first_number(self):
        self.assertFalse(
            _condition_matches(
                self.runtime,
                "1200х800х740 мм",
                "1200х1000",
                "Размер внешний",
            )
        )

    def test_matching_leading_dimensions_are_accepted(self):
        self.assertTrue(
            _condition_matches(
                self.runtime,
                "1200х800х740 мм",
                "1200х800",
                "Размер внешний",
            )
        )
