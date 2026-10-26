from django.test import TestCase
from django.utils import timezone
from .iprice_models import IPricePriceImport, NomenclaturePrice
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotProduct
from .iprice_catalog import build_products
from .iprice_filters import filter_products, filter_options, EMPTY


class CatalogTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate()
        batch = IPricePriceImport.objects.create(date=self.day, filename='test.xlsx', checksum='test', rows=3)
        for code, region, group in [('001-A', 'Moscow', 'Boxes'), ('001-A', 'SPB', 'Boxes'), ('002', 'Moscow', 'Tanks')]:
            NomenclaturePrice.objects.create(batch=batch, date=self.day, code=code, shipp_region=region,
                                            nom=code, group_1='Root', group_2=group, retail=100)
        self.snapshot = IPriceSnapshot.objects.create(calculation_date=self.day, version_number=1,
                                                     revision_for_date=1, status='building')

    def test_all_price_codes_survive_missing_website_and_classification(self):
        result = build_products(self.snapshot)
        self.assertEqual(result['products_created'], 2)
        self.assertEqual(self.snapshot.products.count(), 2)
        for product in self.snapshot.products.all():
            self.assertIsNone(product.base_product_key)
            self.assertFalse(product.is_classified)
            self.assertEqual(product.pricing_method, 'exclusive')
            self.assertIn('MISSING_CLASSIFICATION', product.warning_codes)
            self.assertIn('MISSING_WEBSITE_PRODUCT', product.warning_codes)
        build_products(self.snapshot)
        self.assertEqual(self.snapshot.products.count(), 2)

    def test_groups_classification_and_search_intersect(self):
        build_products(self.snapshot)
        IPriceSnapshotProduct.objects.filter(code_1c='001-A').update(is_classified=True, category='Plastic')
        qs = self.snapshot.products.all()
        self.assertEqual(filter_products(qs, {'group_2': ['Boxes'], 'category': ['Plastic']}).count(), 1)
        self.assertEqual(filter_products(qs, {'group_2': ['Boxes'], 'is_classified': ['false']}).count(), 0)
        self.assertEqual(filter_products(qs, {'is_classified': ['false'], 'group_4': [EMPTY]}).get().code_1c, '002')
        options = filter_options(qs, {'group_2': ['Boxes']}, search='001')
        self.assertEqual(options['category'], ['Plastic'])
        self.assertEqual(options['group_2'], ['Boxes'])
        with self.assertRaises(ValueError):
            filter_products(qs, {'unknown': ['value']})

    def test_regional_rows_without_site_use_purchase_and_delivery_per_region(self):
        from decimal import Decimal
        from .iprice_models import IPriceRegionalInput
        from .iprice_regional_calculation import build_regions
        build_products(self.snapshot)
        defaults = dict(month=self.day.replace(day=1), code='001-A', purchase_cost=100,
                        base_analog=1, base_exclusive='.3', minimum_margin='.1', small='.1', medium='.15', large='.2')
        IPriceRegionalInput.objects.create(region='Moscow', **defaults)
        IPriceRegionalInput.objects.create(region='SPB', include_transport=True, logistics_unit='12.34', **defaults)
        self.assertEqual(build_regions(snapshot=self.snapshot)['regions_created'], 3)
        product = self.snapshot.products.get(code_1c='001-A')
        self.assertEqual(product.regions.get(sale_region='Moscow').cost_with_logistics, 100)
        self.assertEqual(product.regions.get(sale_region='SPB').cost_with_logistics, Decimal('112.34'))
        self.assertIsNone(product.regions.get(sale_region='SPB').quantity_eurotruck)
        self.assertEqual(product.regions.get(sale_region='SPB').calculated_rrp, 160)
        missing = self.snapshot.products.get(code_1c='002').regions.get()
        self.assertEqual(missing.calculation_status, 'error')
        self.assertIn('INVALID_PURCHASE_COST', missing.error_codes)
        self.assertIsNone(missing.calculated_rrp)

    def test_sam_is_saved_without_website_and_old_snapshot_is_immutable(self):
        NomenclaturePrice.objects.filter(code="001-A").update(assortment_matrix_status="Active")
        build_products(self.snapshot)
        product = self.snapshot.products.get(code_1c="001-A")
        self.assertEqual(product.assortment_matrix_status, "Active")
        NomenclaturePrice.objects.filter(code="001-A").update(assortment_matrix_status=None)
        product.refresh_from_db()
        self.assertEqual(product.assortment_matrix_status, "Active")
        self.assertIsNone(self.snapshot.products.get(code_1c="002").assortment_matrix_status)
