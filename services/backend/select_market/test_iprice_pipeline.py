from unittest.mock import patch
from django.test import TestCase, override_settings
from datasets.models import ParserMasterPipelineRun as LegacyMaster
from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.iprice_workspace import IPriceWorkspace
from datasets.services.parsers import master_pipeline, tara_jobs, tara_remote, global_queue
from organizations.models import Organization
from .iprice_pipeline import create_master
from .iprice_tara_models import TaraRun
from .test_iprice_tt import InlineExecutor


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True, TARA_PARSER_WORKERS=1, TARA_WORKER_WAIT_HOURS=4)
class MasterPipelineTests(TestCase):
    def setUp(self):
        self.sm = Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.iplast = Organization.objects.create(code='iplast', name='Iplast', postgres_schema='public')
        self.workspace = IPriceWorkspace('select-market')
        self.legacy = LegacyMaster.objects.create(status='queued')

    def finish_child(self):
        with patch.object(tara_jobs, 'launch'), self.captureOnCommitCallbacks(execute=True):
            tara_jobs.dispatch(workspace=self.workspace)
        child = TaraRun.objects.get(status='dispatching')
        with patch.object(tara_remote, 'available', return_value=True), patch.object(tara_jobs, 'ThreadPoolExecutor', InlineExecutor), patch.object(tara_jobs, 'kick'):
            tara_jobs.execute(child.pk, child.lease, workspace=self.workspace)
        child.refresh_from_db()
        self.assertEqual(child.status, 'success')

    def test_complete_pipeline_resumes_without_repeating_sources(self):
        run = create_master()
        self.assertEqual(create_master().pk, run.pk)
        with patch('select_market.iprice_pipeline.base_parser.load_base_products', return_value={'loaded': 1}) as base, patch('select_market.iprice_pipeline.tt_product_parser.parse_tt_products', return_value={'failed': 0}) as tt, patch('select_market.iprice_pipeline.ps_product_parser.parse_ps_products', return_value={'failed': 0}) as ps, patch.object(tara_jobs, 'kick'), patch.object(master_pipeline, 'send_bitrix_message') as notify, patch.object(master_pipeline, 'publish_iprice_update') as publish:
            for expected in ('waiting_tara', 'waiting_tara', 'success'):
                result = master_pipeline.run_parser_master_pipeline(run_id=run.pk, workspace=self.workspace)
                self.assertEqual(result['status'], expected)
                if expected == 'waiting_tara':
                    self.assertEqual(ParserQueueEntry.objects.get().status, 'waiting_remote')
                    self.finish_child()
            base.assert_called_once_with(workspace=self.workspace)
            self.assertEqual(tt.call_count, 1)
            self.assertEqual(ps.call_count, 1)
            self.assertEqual(tt.call_args.kwargs['workspace'], self.workspace)
            notify.assert_not_called()
            publish.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(len(run.result['completed_steps']), 9)
        self.assertIn('source_results', run.result)
        self.assertEqual(ParserQueueEntry.objects.get().status, 'success')
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, 'queued')

    def test_busy_iplast_slot_prevents_any_source_work(self):
        global_queue.enqueue(organization=self.iplast, kind='master', run_id=self.legacy.pk)
        global_queue.claim_next(executor='iplast')
        run = create_master()
        with patch('select_market.iprice_pipeline.base_parser.load_base_products') as base:
            result = master_pipeline.run_parser_master_pipeline(run_id=run.pk, workspace=self.workspace)
        self.assertTrue(result['waiting_for_capacity'])
        base.assert_not_called()

    def test_failure_stops_following_sources_and_releases_slot(self):
        run = create_master()
        with patch('select_market.iprice_pipeline.base_parser.load_base_products', side_effect=ValueError('invalid feed')), patch('select_market.iprice_pipeline.tt_product_parser.parse_tt_products') as tt:
            with self.assertRaises(master_pipeline.ParserMasterPipelineError):
                master_pipeline.run_parser_master_pipeline(run_id=run.pk, workspace=self.workspace)
        tt.assert_not_called()
        self.assertEqual(ParserQueueEntry.objects.get().status, 'failed')

    def test_queued_master_dispatch_uses_organization(self):
        from datasets.services.parsers.queue_execution import dispatch_waiting_masters
        run = create_master()
        with patch('datasets.services.parsers.master_pipeline_launcher.launch_parser_master_pipeline') as launch:
            dispatch_waiting_masters()
        launch.assert_called_once_with(run.pk, workspace=self.workspace)

    def test_retry_selects_only_failed_items_from_first_tara_pass(self):
        from .iprice_domain_models import ParserProductUrl, ParserProductClassification
        for number in range(2):
            url = ParserProductUrl.objects.create(source='tara', url=f'https://tara.ru/catalog/{number}/', status='active')
            ParserProductClassification.objects.create(product_key=url.pk, status='active', item_type='product')
        run = create_master()
        with patch('select_market.iprice_pipeline.base_parser.load_base_products', return_value={}), patch('select_market.iprice_pipeline.tt_product_parser.parse_tt_products', return_value={'failed': 0}), patch('select_market.iprice_pipeline.ps_product_parser.parse_ps_products', return_value={'failed': 0}), patch.object(tara_jobs, 'kick'):
            master_pipeline.run_parser_master_pipeline(run_id=run.pk, workspace=self.workspace)
            first = TaraRun.objects.get()
            items = list(first.items.order_by('id'))
            first.items.filter(pk=items[0].pk).update(status='error')
            first.items.filter(pk=items[1].pk).update(status='success')
            ParserProductUrl.objects.filter(pk=items[0].product_id).update(is_loaded=False, last_error='network')
            TaraRun.objects.filter(pk=first.pk).update(status='success')
            master_pipeline.run_parser_master_pipeline(run_id=run.pk, workspace=self.workspace)
        retry = TaraRun.objects.exclude(pk=first.pk).get()
        self.assertEqual(list(retry.items.values_list('product_id', flat=True)), [items[0].product_id])
