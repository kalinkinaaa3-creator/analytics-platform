from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from datasets.models import TaraRun as LegacyRun, TaraFetch as LegacyFetch, TaraProductPrice as LegacyPrice
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers import tara_remote, global_queue
from datasets.services.parsers.tara_product_parser import save_product_data
from organizations.models import Organization
from .iprice_tara_models import TaraRun, TaraFetch
from .iprice_domain_models import ParserProductUrl, TaraProductPrice


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True)
class TaraTransportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.workspace = IPriceWorkspace('select-market')
        self.run = TaraRun.objects.create(status='running', lease='local', request_key='local')
        self.legacy_run = LegacyRun.objects.create(id=self.run.pk, status='running', lease='legacy', request_key='legacy')
        self.task = TaraFetch.objects.create(run=self.run, run_lease='local', url='https://tara.ru/product', expires_at=timezone.now()+timedelta(minutes=5))
        self.legacy_task = LegacyFetch.objects.create(id=self.task.pk, run=self.legacy_run, run_lease='legacy', url='https://tara.ru/legacy', expires_at=self.task.expires_at)
        global_queue.enqueue(organization=self.org, kind='tara', run_id=self.run.pk)
        self.owner = global_queue.claim_next(executor='test')

    def payload(self):
        return {'status': 200, 'html': '<html>product</html>', 'final_url': self.task.url}

    def claim(self):
        return tara_remote.claim('a'*32, True, workspace=self.workspace)[0]

    def test_matching_ids_are_isolated_and_completion_is_idempotent(self):
        claimed = self.claim()
        tara_remote.complete(self.task.pk, claimed['token'], self.payload(), workspace=self.workspace)
        tara_remote.complete(self.task.pk, claimed['token'], self.payload(), workspace=self.workspace)
        self.task.refresh_from_db()
        self.legacy_task.refresh_from_db()
        self.assertEqual(self.task.status, 'done')
        self.assertEqual(self.legacy_task.status, 'pending')
        with self.assertRaises(ValueError):
            tara_remote.complete(self.task.pk, claimed['token'], self.payload())

    def test_old_run_lease_rejects_result(self):
        claimed = self.claim()
        TaraRun.objects.filter(pk=self.run.pk).update(lease='new')
        with self.assertRaises(ValueError):
            tara_remote.complete(self.task.pk, claimed['token'], self.payload(), workspace=self.workspace)

    def test_lost_capacity_rejects_result(self):
        claimed = self.claim()
        global_queue.finish(self.owner.pk, self.owner.token, success=False)
        with self.assertRaises(ValueError):
            tara_remote.complete(self.task.pk, claimed['token'], self.payload(), workspace=self.workspace)

    def test_capacity_limit_counts_both_schemas(self):
        for i in range(5):
            LegacyFetch.objects.create(run=self.legacy_run, run_lease='legacy', status='claimed', url=f'https://tara.ru/{i}', expires_at=self.task.expires_at)
        self.assertEqual(tara_remote.claim('a'*32, True, workspace=self.workspace), [])

    def test_second_worker_is_rejected_across_organizations(self):
        self.claim()
        with self.assertRaises(ValueError):
            tara_remote.claim('b'*32, True)

    def test_prices_use_local_tables(self):
        product = ParserProductUrl.objects.create(source='tara', url=self.task.url, status='active')
        save_product_data(product, [], [{'price': 122, 'final_price': 100}], workspace=self.workspace)
        self.assertEqual(TaraProductPrice.objects.get().final_price, 100)
        self.assertFalse(LegacyPrice.objects.exists())
