"""Acceptance checks requiring the dedicated iprice_postgres_settings database."""
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import DatabaseError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from organizations.models import Organization
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
from .iprice_recovery import acquire_worker_lock


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL acceptance database')
class PostgreSQLMigrationTests(TransactionTestCase):
    def test_archive_migrations_round_trip_with_two_routes_and_approvals(self):
        from datetime import date
        from decimal import Decimal
        from django.db.migrations.executor import MigrationExecutor
        self.assertEqual(connection.settings_dict['NAME'], 'test_iprice_acceptance')
        before = [('select_market', '0008_regional_purchase_inputs')]
        after = [('select_market', '0012_archive_legacy_routes')]

        def migrate(target):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            return executor.loader.project_state(target).apps

        try:
            old = migrate(before)
            get = lambda name: old.get_model('select_market', name)
            snapshot = get('IPriceSnapshot').objects.create(calculation_date=date(2026, 10, 1), version_number=1, revision_for_date=1,
                status='success', is_active=True, was_active=True)
            product = get('IPriceSnapshotProduct').objects.create(snapshot=snapshot, base_product_key=None, code_1c='001-A', nom='Product', pricing_method='exclusive')
            rows = []
            for index, plant in enumerate(('Plant A', 'Plant B'), 1):
                row = get('IPriceSnapshotRegion').objects.create(snapshot_product=product, sale_region='Region', departure=plant,
                    calculated_distr=Decimal('123.4567'), transport_cost=Decimal('987.6543'))
                approval = get('IPriceSnapshotApproval').objects.create(snapshot_region=row, revision=1, approved_rrp=150,
                    approved_distr=Decimal('120.1234'), comment=plant)
                rows.append((row.pk, approval.pk, plant, approval.approved_at))
            cost = get('ProductCost').objects.create(date=date(2026, 10, 1), code='001-A', departure='Plant A', cost=Decimal('50.1234'))
            batch = get('IPricePriceImport').objects.create(date=date(2026, 10, 1), filename='old.xlsx', checksum='test', rows=1)
            price = get('NomenclaturePrice').objects.create(batch=batch, date=batch.date, code='001-A', shipp_region='Region', distr=Decimal('100.1234'))
            new = migrate(after)
            regions = new.get_model('select_market', 'IPriceSnapshotRegion')
            self.assertEqual(regions.objects.filter(snapshot_product_id=product.pk).count(), 2)
            self.assertEqual(len(set(regions.objects.values_list('historical_variant', flat=True))), 2)
            self.assertNotIn('departure', {field.name for field in regions._meta.fields})
            self.assertTrue(new.get_model('select_market', 'IPriceSnapshot').objects.get(pk=snapshot.pk).is_active)
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('select_market.product_cost')")
                self.assertIsNone(cursor.fetchone()[0])
            old = migrate(before)
            for row_id, approval_id, plant, approved_at in rows:
                row = old.get_model('select_market', 'IPriceSnapshotRegion').objects.get(pk=row_id)
                approval = old.get_model('select_market', 'IPriceSnapshotApproval').objects.get(pk=approval_id)
                self.assertEqual(row.departure, plant)
                self.assertEqual(row.calculated_distr, Decimal('123.4567'))
                self.assertEqual(row.transport_cost, Decimal('987.6543'))
                self.assertEqual(approval.snapshot_region_id, row_id)
                self.assertEqual(approval.approved_distr, Decimal('120.1234'))
                self.assertEqual(approval.approved_at, approved_at)
            self.assertEqual(old.get_model('select_market', 'ProductCost').objects.get(pk=cost.pk).cost, Decimal('50.1234'))
            self.assertEqual(old.get_model('select_market', 'NomenclaturePrice').objects.get(pk=price.pk).distr, Decimal('100.1234'))
            next_cost = old.get_model('select_market', 'ProductCost').objects.create(date=date(2026, 10, 1), code='002-A', departure='Plant A', cost=1)
            self.assertGreater(next_cost.pk, cost.pk)
            migrate(after)
        finally:
            migrate(after)


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL acceptance database')
class PostgreSQLAcceptanceTests(TestCase):
    def other_connection(self, operation):
        def work():
            try:
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(work).result(timeout=15)

    def test_recovery_refuses_while_worker_holds_lock(self):
        acquire_worker_lock()
        def compete():
            with transaction.atomic():
                try:
                    acquire_worker_lock()
                except ValueError:
                    return 'blocked'
            return 'unsafe'
        self.assertEqual(self.other_connection(compete), 'blocked')

    def test_edit_activation_and_import_share_organization_lock(self):
        _lock_snapshot_workspace(IPriceWorkspace('select-market'))
        def compete():
            try:
                with transaction.atomic():
                    Organization.objects.select_for_update(nowait=True).get(code='select-market')
            except DatabaseError:
                return 'blocked'
            return 'unsafe'
        self.assertEqual(self.other_connection(compete), 'blocked')

    def test_models_use_separate_physical_tables(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.iprice_snapshot')::oid, to_regclass('select_market.iprice_snapshot')::oid")
            legacy, selected = cursor.fetchone()
        self.assertIsNotNone(legacy)
        self.assertIsNotNone(selected)
        self.assertNotEqual(legacy, selected)
