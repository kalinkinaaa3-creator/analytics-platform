import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch, Mock

from django.test import TestCase, override_settings
from django.utils import timezone
from datasets.models import ParserProductUrl, TaraRun, TaraItem, TaraSession, TaraProductPrice, ParserMasterPipelineRun
from datasets.services.parsers import tara_jobs as jobs
from datasets.services.parsers.tara_product_parser import (
    fetch_html_via_browser, BrowserBlockedError, ProductNotFoundError, BrowserServiceError,
)


def state():
    return {'cookies': [{'name': 'test', 'value': 'secret', 'domain': '.tara.ru',
                         'path': '/', 'expires': -1}], 'origins': []}


@override_settings(TARA_SESSION_WAIT_HOURS=4, TARA_SERVICE_KEY='test',
                   TARA_BROWSER_SERVICE_URL='http://browser', TARA_PARSER_WORKERS=1)
class TaraJobsTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(TARA_SESSION_DIR=Path(self.tmp.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        for name in ('notify', 'publish', 'kick', 'launch'):
            p = patch.object(jobs, name)
            p.start()
            self.addCleanup(p.stop)
        self.product = ParserProductUrl.objects.create(source='tara', url='https://spb.tara.ru/catalog/a/')

    def run_job(self, **kwargs):
        return TaraRun.objects.create(request_key='test', status='running', lease='lease', **kwargs)

    def test_selection_daily_and_classified(self):
        ParserProductUrl.objects.create(source='tara', url='https://spb.tara.ru/today/', is_loaded=True, date_update=timezone.now())
        run = jobs.create_run(request_key='all')
        self.assertEqual(list(run.items.values_list('product_id', flat=True)), [self.product.pk])
        run.status = 'success'; run.save()
        with patch('datasets.services.parsers.product_key_selector.get_active_classified_product_keys', return_value=set()):
            selected = jobs.create_run(request_key='classified', options={'classified_only': True})
        self.assertEqual(selected.items.count(), 0)

    def test_one_active_run_and_idempotent_request(self):
        run = jobs.create_run(request_key='first')
        self.assertEqual(jobs.create_run(request_key='first').pk, run.pk)
        with self.assertRaises(jobs.TaraPending):
            jobs.create_run(request_key='second')

    def test_wait_deadline_not_extended(self):
        run = self.run_job()
        jobs.set_waiting(run, 'blocked')
        run.refresh_from_db()
        first = run.wait_until
        self.assertAlmostEqual((first - timezone.now()).total_seconds(), 14400, delta=3)
        jobs.set_waiting(run, 'still blocked')
        run.refresh_from_db()
        self.assertEqual(run.wait_until, first)
        self.assertEqual(jobs.notify.call_count, 1)

    def test_valid_upload_queues_same_run_and_preserves_success(self):
        run = self.run_job()
        TaraItem.objects.create(run=run, product=self.product, status='success')
        jobs.set_waiting(run, 'blocked')
        candidate = jobs.upload(run.pk, json.dumps(state()).encode(), None)
        candidate.status = 'checking'; candidate.save()
        with patch.object(jobs, 'browser_post', return_value={'valid': True}):
            jobs.check_session(candidate)
        run.refresh_from_db()
        self.assertEqual(run.status, 'queued')
        self.assertEqual(run.session_id, candidate.pk)
        self.assertEqual(run.items.get().status, 'success')
        self.assertIsNone(run.wait_until)

    def test_rejected_upload_does_not_reset_deadline(self):
        run = self.run_job(); jobs.set_waiting(run, 'blocked'); run.refresh_from_db()
        deadline = run.wait_until
        candidate = jobs.upload(run.pk, json.dumps(state()).encode(), None)
        candidate.status = 'checking'; candidate.save()
        with patch.object(jobs, 'browser_post', return_value={'valid': False}):
            jobs.check_session(candidate)
        run.refresh_from_db()
        self.assertEqual(run.status, 'waiting_session')
        self.assertEqual(run.wait_until, deadline)
        self.assertFalse((Path(self.tmp.name) / candidate.filename).exists())

    def test_expiry_finishes_parent_and_rejects_late_upload(self):
        parent = ParserMasterPipelineRun.objects.create(status='waiting_session')
        run = self.run_job(master=parent)
        run.status = 'waiting_session'; run.wait_until = timezone.now() - timedelta(seconds=1); run.lease = ''; run.save()
        jobs.dispatch()
        run.refresh_from_db(); parent.refresh_from_db()
        self.assertEqual((run.status, parent.status), ('failed', 'failed'))
        with self.assertRaises(ValueError): jobs.upload(run.pk, json.dumps(state()).encode(), None)

    def test_cancel_during_validation_cannot_resume(self):
        run = self.run_job(); jobs.set_waiting(run, 'blocked')
        candidate = jobs.upload(run.pk, json.dumps(state()).encode(), None)
        candidate.status = 'checking'; candidate.save()
        run.refresh_from_db(); jobs.finish(run, 'cancelled', 'cancelled')
        with patch.object(jobs, 'browser_post', return_value={'valid': True}): jobs.check_session(candidate)
        run.refresh_from_db()
        self.assertEqual(run.status, 'cancelled')

    def test_duplicate_upload_is_rejected(self):
        run = self.run_job(); jobs.set_waiting(run, 'blocked')
        jobs.upload(run.pk, json.dumps(state()).encode(), None)
        with self.assertRaises(ValueError): jobs.upload(run.pk, json.dumps(state()).encode(), None)

    def test_404_terminal_but_blocked_remains_pending(self):
        run = self.run_job()
        item = TaraItem.objects.create(run=run, product=self.product, status='running')
        with patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', side_effect=BrowserBlockedError('blocked')):
            self.assertEqual(jobs.process_item(item.pk, run.pk, run.lease, 'file'), 'blocked')
        item.refresh_from_db(); self.assertEqual(item.status, 'pending')
        with patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', side_effect=ProductNotFoundError('HTTP 404: product page not found')):
            self.assertEqual(jobs.process_item(item.pk, run.pk, run.lease, 'file'), 'not_found')
        self.product.refresh_from_db(); self.assertEqual(self.product.status, 'inactive')

    def test_card_without_price_still_saved(self):
        run = self.run_job()
        item = TaraItem.objects.create(run=run, product=self.product, status='running')
        html = '<body><div class="topic__heading"><h1 id="pagetitle">Product</h1></div></body>'
        with patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', return_value=html):
            self.assertEqual(jobs.process_item(item.pk, run.pk, run.lease, 'file'), 'success')
        self.assertIsNone(TaraProductPrice.objects.get(product_key=self.product.pk).price)

    def test_cancelled_lease_cannot_write_prices(self):
        run = self.run_job(); item = TaraItem.objects.create(run=run, product=self.product)
        jobs.finish(run, 'cancelled', 'cancelled')
        with patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', return_value='<body class="topic__heading"></body>'):
            self.assertEqual(jobs.process_item(item.pk, run.pk, 'lease', 'file'), 'stale')
        self.assertFalse(TaraProductPrice.objects.exists())

    def test_foreign_cookie_and_bad_json_rejected(self):
        data = state(); data['cookies'][0]['domain'] = '.tara.ru.evil.test'
        with self.assertRaises(ValueError): jobs.normalize_state(json.dumps(data).encode())
        with self.assertRaises(ValueError): jobs.normalize_state(b'null')

    def test_fetch_404_block_and_invalid_html(self):
        for status, html, exception in [
            (404, '<body>Not found</body>', ProductNotFoundError),
            (403, '<body>Forbidden</body>', BrowserBlockedError),
            (200, '<body>Something else</body>', BrowserServiceError),
        ]:
            response = Mock(); response.json.return_value = {'status': status, 'html': html}
            with patch('datasets.services.parsers.tara_product_parser.requests.post', return_value=response):
                with self.assertRaises(exception): fetch_html_via_browser(self.product.url, 'file')

    def test_empty_sitemap_cannot_inactivate_links(self):
        from datasets.services.parsers.tara_sitemap import sync_tara_sitemap_to_product_urls
        with patch('datasets.services.parsers.tara_sitemap.fetch_sitemap_xml', return_value=b'<urlset/>'):
            with self.assertRaises(RuntimeError): sync_tara_sitemap_to_product_urls()
        self.product.refresh_from_db(); self.assertEqual(self.product.status, 'active')

    def test_resume_processes_only_remaining_items(self):
        from concurrent.futures import Future
        class InlinePool:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def submit(self, fn, *args):
                result = Future()
                try: result.set_result(fn(*args))
                except Exception as exc: result.set_exception(exc)
                return result
        second = ParserProductUrl.objects.create(source='tara', url='https://kazan.tara.ru/catalog/b/')
        run = jobs.create_run(request_key='resume', options={'workers': 1})
        session = TaraSession.objects.create(run=run, filename='a' * 32 + '.json', status='valid')
        run.session = session; run.status = 'dispatching'; run.lease = 'first'; run.save()
        html = '<body><div class="topic__heading"><h1 id="pagetitle">Product</h1></div></body>'
        with patch.object(jobs, 'ThreadPoolExecutor', InlinePool), patch('datasets.services.parsers.product_image_sync.sync_parser_source_images'), patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', side_effect=[html, BrowserBlockedError('blocked')]):
            jobs.execute(run.pk, 'first')
        run.refresh_from_db()
        self.assertEqual(run.status, 'waiting_session')
        self.assertEqual(run.items.get(product=self.product).status, 'success')
        deadline = run.wait_until
        candidate = jobs.upload(run.pk, json.dumps(state()).encode(), None)
        candidate.status = 'checking'; candidate.save()
        with patch.object(jobs, 'browser_post', return_value={'valid': True}): jobs.check_session(candidate)
        run.refresh_from_db(); run.status = 'dispatching'; run.lease = 'second'; run.save()
        with patch.object(jobs, 'ThreadPoolExecutor', InlinePool), patch('datasets.services.parsers.product_image_sync.sync_parser_source_images'), patch('datasets.services.parsers.tara_product_parser.fetch_html_via_browser', return_value=html) as fetch:
            jobs.execute(run.pk, 'second')
        run.refresh_from_db()
        self.assertEqual(run.status, 'success')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0], second.url)
        self.assertEqual(run.items.get(product=self.product).attempts, 1)

    def test_stale_runner_requeued_with_new_lease(self):
        run = self.run_job(heartbeat=timezone.now() - timedelta(minutes=8))
        item = TaraItem.objects.create(run=run, product=self.product, status='running')
        with self.captureOnCommitCallbacks(execute=True): jobs.dispatch()
        run.refresh_from_db(); item.refresh_from_db()
        self.assertEqual(run.status, 'dispatching')
        self.assertNotEqual(run.lease, 'lease')
        self.assertEqual(item.status, 'pending')
        jobs.launch.assert_called_once()

    def test_master_resume_skips_completed_steps(self):
        from datasets.services.parsers.master_pipeline import _run_command
        parent = ParserMasterPipelineRun.objects.create(result={'completed_steps': ['base_parser', 'tt_parser']})
        with patch('datasets.services.parsers.master_pipeline.call_command') as command:
            _run_command(parent, step_name='base_parser', command_name='load_base_products')
            command.assert_not_called()

    def test_upload_requires_edit_permission(self):
        from django.contrib.auth import get_user_model
        from dashboards.models import Dashboard, DashboardAccess
        from rest_framework.test import APIRequestFactory, force_authenticate
        from datasets.api.tara_views import TaraSessionUploadView, TaraStatusView
        viewer = get_user_model().objects.create_user(username='tara-viewer')
        dashboard = Dashboard.objects.create(name='iPrice', slug='iprice')
        DashboardAccess.objects.create(user=viewer, dashboard=dashboard, can_view=True, can_edit=False)
        request = APIRequestFactory().post('/session/', {}, format='multipart')
        force_authenticate(request, user=viewer)
        response = TaraSessionUploadView.as_view()(request, run_id=1)
        self.assertEqual(response.status_code, 403)
        request = APIRequestFactory().get('/status/')
        response = TaraStatusView.as_view()(request)
        self.assertIn(response.status_code, (401, 403))

    def test_two_dispatchers_cannot_launch_same_run_twice(self):
        jobs.create_run(request_key='dispatch-once')
        with self.captureOnCommitCallbacks(execute=True):
            jobs.dispatch()
            jobs.dispatch()
        self.assertEqual(jobs.launch.call_count, 1)

    def test_report_is_scoped_to_requested_run(self):
        from django.core.management import call_command
        from io import StringIO
        run = self.run_job()
        TaraItem.objects.create(run=run, product=self.product, status='not_found')
        output = StringIO()
        call_command('report_tara_parser_result', tara_run_id=run.pk, skip_bitrix=True, stdout=output)
        self.assertIn('404: 1', output.getvalue())
        self.assertIn('Total: 1', output.getvalue())
