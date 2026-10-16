from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from datasets.api.tara_worker_views import TaraWorkerClaimView, TaraWorkerResultView
from datasets.models import TaraRun as LegacyRun, TaraFetch as LegacyFetch
from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers import tara_jobs as jobs, tara_remote
from organizations.models import Organization
from .iprice_domain_models import ParserProductUrl, TaraProductPrice
from .iprice_tara_models import TaraRun, TaraFetch
from .test_iprice_tt import InlineExecutor


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True, TARA_WORKER_WAIT_HOURS=4, TARA_PARSER_WORKERS=1, TARA_WORKER_KEY='test-key')
class TaraJobsTests(TestCase):
    def setUp(self):
        Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        Organization.objects.create(code='iplast', name='Iplast', postgres_schema='public')
        self.workspace = IPriceWorkspace('select-market')
        self.product = ParserProductUrl.objects.create(source='tara', url='https://tara.ru/catalog/item/', status='active')
        self.legacy = LegacyRun.objects.create(request_key='same', status='queued')

    def create(self):
        return jobs.create_run(request_key='same', workspace=self.workspace)

    def dispatch(self):
        with patch.object(jobs, 'launch') as launch, self.captureOnCommitCallbacks(execute=True):
            jobs.dispatch(workspace=self.workspace)
        return launch

    def execute(self, run):
        run.refresh_from_db()
        with patch.object(jobs, 'kick'), patch.object(jobs, 'send_bitrix_message') as notify:
            jobs.execute(run.pk, run.lease, workspace=self.workspace)
        notify.assert_not_called()

    def test_creation_idempotence_and_dispatch_arguments(self):
        run = self.create()
        self.assertEqual(self.create().pk, run.pk)
        self.assertEqual(run.items.get().product_id, self.product.pk)
        launch = self.dispatch()
        self.assertEqual(launch.call_args.args[-2:], ('--organization', 'select-market'))
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, 'queued')

    def test_wait_resume_complete_keeps_one_slot(self):
        run = self.create()
        self.dispatch()
        with patch.object(tara_remote, 'available', return_value=False):
            self.execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, 'waiting_session')
        self.assertEqual(ParserQueueEntry.objects.get().status, 'waiting_remote')
        deadline = run.wait_until
        tara_remote.claim('a'*32, True, workspace=self.workspace)
        self.dispatch()
        with patch.object(tara_remote, 'available', return_value=True), patch.object(jobs, 'ThreadPoolExecutor', InlineExecutor), patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', return_value='html'), patch('datasets.services.parsers.tara_product_parser.parse_properties', return_value=[]), patch('datasets.services.parsers.tara_product_parser.parse_price_rows', return_value=[{'price': 122, 'final_price': 100}]):
            self.execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, 'success')
        self.assertEqual(run.wait_until, deadline)
        self.assertEqual(TaraProductPrice.objects.get().final_price, 100)
        self.assertEqual(ParserQueueEntry.objects.get().status, 'success')

    def test_expired_wait_releases_only_parked_slot(self):
        run = self.create()
        self.dispatch()
        with patch.object(tara_remote, 'available', return_value=False):
            self.execute(run)
        TaraRun.objects.filter(pk=run.pk).update(wait_until=timezone.now()-timedelta(seconds=1))
        self.dispatch()
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertEqual(ParserQueueEntry.objects.get().status, 'failed')

    def test_worker_api_routes_by_slot_and_token_without_new_client_fields(self):
        run = self.create()
        self.dispatch()
        from datasets.services.parsers import global_queue
        owner = global_queue.claim_next(executor='test')
        TaraRun.objects.filter(pk=run.pk).update(status='running', lease='local')
        task = TaraFetch.objects.create(run=run, run_lease='local', url=self.product.url, expires_at=timezone.now()+timedelta(minutes=5))
        LegacyFetch.objects.create(id=task.pk, run=self.legacy, run_lease='legacy', url='https://tara.ru/legacy', expires_at=task.expires_at)
        factory = APIRequestFactory()
        request = factory.post('/claim/', {'owner': 'a'*32, 'ready': True}, format='json', HTTP_X_TARA_WORKER_KEY='test-key')
        response = TaraWorkerClaimView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        claimed = response.data['tasks'][0]
        request = factory.post('/result/', {'token': claimed['token'], 'payload': {'status': 200, 'html': 'product', 'final_url': self.product.url}}, format='json', HTTP_X_TARA_WORKER_KEY='test-key')
        response = TaraWorkerResultView.as_view()(request, task_id=task.pk)
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')
        self.assertEqual(LegacyFetch.objects.get().status, 'pending')

    @override_settings(PARSER_SHARED_QUEUE_ENABLED=False)
    def test_disabled_queue_prevents_creation(self):
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse(TaraRun.objects.exists())

    def test_sitemap_only_uses_local_prefixes_and_storage(self):
        from .iprice_domain_models import ParserPrefix
        from datasets.models import ParserProductUrl as LegacyUrl
        ParserPrefix.objects.create(source='tara', prefix='spb')
        legacy = LegacyUrl.objects.create(source='tara', url='https://tara.ru/catalog/legacy/', status='active')
        run = jobs.create_run(request_key='sitemap', workspace=self.workspace, options={'sitemap': True, 'sitemap_only': True})
        self.dispatch()
        xml = b'<urlset><url><loc>https://tara.ru/catalog/new/</loc></url></urlset>'
        with patch.object(tara_remote, 'available', return_value=True), patch('datasets.services.parsers.tara_sitemap.fetch_sitemap_xml', return_value=xml) as fetch:
            self.execute(run)
        self.assertEqual(fetch.call_args.kwargs['workspace'], self.workspace)
        self.assertEqual(fetch.call_args.kwargs['run_id'], run.pk)
        self.assertTrue(ParserProductUrl.objects.filter(url='https://spb.tara.ru/catalog/new/', status='active').exists())
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, 'active')
        self.assertEqual(LegacyUrl.objects.count(), 1)
        self.assertEqual(ParserQueueEntry.objects.get().status, 'success')

    def test_stale_process_does_not_save_product_data(self):
        run = self.create()
        TaraRun.objects.filter(pk=run.pk).update(status='running', lease='new')
        with patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', return_value='html'), patch('datasets.services.parsers.tara_product_parser.parse_properties', return_value=[]), patch('datasets.services.parsers.tara_product_parser.parse_price_rows', return_value=[{'final_price': 100}]):
            result = jobs.process_item(run.items.get().pk, run.pk, 'old', workspace=self.workspace)
        self.assertEqual(result, 'stale')
        self.assertFalse(TaraProductPrice.objects.exists())
