"""Exercise archive data conversion with real DB rows; DDL requires PostgreSQL."""
from datetime import date
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import isolate_apps
from django.db import models
from datasets.models import ProductCost, TransportCost
from .iprice_models import IPriceLegacyArchive


class RouteArchiveTests(TransactionTestCase):
    @isolate_apps()
    def test_two_routes_round_trip_without_merging_rows(self):
        class HistoricalRegion(models.Model):
            snapshot_product_id = models.BigIntegerField()
            sale_region = models.CharField(max_length=255)
            departure = models.CharField(max_length=255, null=True)
            historical_variant = models.CharField(max_length=64, default='')
            calculation_config_source_id = models.BigIntegerField(null=True)
            departure_discount_source_id = models.BigIntegerField(null=True)
            transport_cost_source_id = models.BigIntegerField(null=True)
            transport_cost = models.DecimalField(max_digits=18, decimal_places=4, null=True)

            class Meta:
                app_label = 'archive_test'
                db_table = 'test_sm_route_archive'

        migration = import_module('select_market.migrations.0012_archive_legacy_routes')
        registry = SimpleNamespace(get_model=lambda label, name: IPriceLegacyArchive if name == 'IPriceLegacyArchive' else HistoricalRegion)
        with connection.schema_editor() as editor:
            editor.create_model(HistoricalRegion)
        try:
            for route in ('Plant A', 'Plant B'):
                HistoricalRegion.objects.create(snapshot_product_id=1, sale_region='Region', departure=route, transport_cost=Decimal('123.4567'))
            before = list(HistoricalRegion.objects.order_by('id').values('id', *migration.FIELDS))
            migration.archive_routes(registry, SimpleNamespace(connection=connection))
            variants = list(HistoricalRegion.objects.values_list('historical_variant', flat=True))
            self.assertEqual(len(set(variants)), 2)
            self.assertTrue(all(len(value) == 64 for value in variants))
            HistoricalRegion.objects.update(departure=None, transport_cost=None)
            migration.restore_routes(registry, SimpleNamespace(connection=connection))
            self.assertEqual(list(HistoricalRegion.objects.order_by('id').values('id', *migration.FIELDS)), before)
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(HistoricalRegion)


class ArchiveTests(TestCase):
    def test_snapshot_distributors_round_trip_keeps_approval_identity(self):
        from datasets.models import IPriceSnapshot, IPriceSnapshotProduct, IPriceSnapshotRegion, IPriceSnapshotApproval
        migration = import_module('select_market.migrations.0011_archive_snapshot_distributors')
        registry = SimpleNamespace(get_model=lambda label, name: IPriceLegacyArchive if name == 'IPriceLegacyArchive' else apps.get_model('datasets', name))
        snapshot = IPriceSnapshot.objects.create(calculation_date=date(2026, 10, 1), version_number=1, revision_for_date=1)
        product = IPriceSnapshotProduct.objects.create(snapshot=snapshot, base_product_key=1, code_1c=123, nom='Product', pricing_method='exclusive')
        region = IPriceSnapshotRegion.objects.create(snapshot_product=product, sale_region='Region', departure='Plant', calculated_distr=Decimal('123.4567'), discount_distr=Decimal('.123456'))
        approval = IPriceSnapshotApproval.objects.create(snapshot_region=region, revision=1, approved_rrp=150, approved_distr=Decimal('125.1234'), comment='Original')
        editor = SimpleNamespace(connection=connection)
        migration.archive_fields(registry, editor)
        IPriceSnapshotRegion.objects.update(calculated_distr=None, discount_distr=None)
        IPriceSnapshotApproval.objects.update(approved_distr=None)
        migration.restore_fields(registry, editor)
        region.refresh_from_db(); approval.refresh_from_db()
        self.assertEqual(region.calculated_distr, Decimal('123.4567'))
        self.assertEqual(region.discount_distr, Decimal('.123456'))
        self.assertEqual(approval.approved_distr, Decimal('125.1234'))
        self.assertEqual(approval.comment, 'Original')
        self.assertEqual(approval.snapshot_region_id, region.pk)

    def test_price_fields_round_trip_and_reapply(self):
        from datasets.models import NomenclaturePrice
        migration = import_module('select_market.migrations.0010_archive_price_distributors')
        registry = SimpleNamespace(get_model=lambda label, name: IPriceLegacyArchive if name == 'IPriceLegacyArchive' else NomenclaturePrice)
        row = NomenclaturePrice.objects.create(date=date(2026, 10, 1), code=123, shipp_region='Region', distr=Decimal('123.4567'), distr_1=Decimal('120'))
        editor = SimpleNamespace(connection=connection)
        migration.archive_prices(registry, editor)
        NomenclaturePrice.objects.update(distr=None, distr_1=None)
        migration.restore_prices(registry, editor)
        row.refresh_from_db()
        self.assertEqual(row.distr, Decimal('123.4567'))
        self.assertEqual(row.distr_1, Decimal('120'))
        migration.archive_prices(registry, editor)
        self.assertEqual(IPriceLegacyArchive.objects.count(), 1)

    def test_source_round_trip_preserves_decimal_ids_and_timestamp(self):
        migration = import_module('select_market.migrations.0009_archive_retired_sources')
        # Legacy test tables provide the retired schema, never production data.
        registry = SimpleNamespace(get_model=lambda label, name: IPriceLegacyArchive if name == 'IPriceLegacyArchive' else apps.get_model('datasets', name))
        cost = ProductCost.objects.create(date=date(2026, 10, 1), code=123, departure='Plant', cost=Decimal('123.4567'))
        route = TransportCost.objects.create(departure='Plant', arrival='Region', cost=Decimal('987.6543'))
        original_cost = ProductCost.objects.values().get(pk=cost.pk)
        original_route = TransportCost.objects.values().get(pk=route.pk)
        editor = SimpleNamespace(connection=connection, execute=lambda sql: None)
        migration.archive_sources(registry, editor)
        self.assertEqual(IPriceLegacyArchive.objects.count(), 2)
        self.assertEqual(IPriceLegacyArchive.objects.get(source_model='ProductCost').payload['cost'], '123.4567')
        ProductCost.objects.all().delete()
        TransportCost.objects.all().delete()
        migration.restore_sources(registry, editor)
        self.assertEqual(ProductCost.objects.values().get(pk=cost.pk), original_cost)
        self.assertEqual(TransportCost.objects.values().get(pk=route.pk), original_route)
