from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from datasets.models import TaraRun, TaraFetch, TaraWorker
from datasets.services.parsers import tara_remote as remote


class TaraRemoteTests(TestCase):
    def setUp(self):
        self.run = TaraRun.objects.create(request_key='remote-test',status='running',lease='run-lease')
        self.url = 'https://moskva.tara.ru/catalog/a/?oid=123'

    def task(self):
        return TaraFetch.objects.create(run=self.run,run_lease=self.run.lease,url=self.url,
                                       expires_at=timezone.now()+timedelta(minutes=3))

    def payload(self):
        return {'status':200,'html':'<body class="topic__heading">product</body>','final_url':self.url}

    def test_one_owner_and_five_inflight(self):
        for _ in range(7): self.task()
        self.assertEqual(len(remote.claim('a'*32,True)),5)
        self.assertEqual(remote.claim('a'*32,True),[])
        with self.assertRaises(ValueError): remote.claim('b'*32,True)

    def test_heartbeat_does_not_consume_tasks(self):
        task=self.task()
        self.assertEqual(remote.claim('a'*32,True,pull=False),[])
        task.refresh_from_db(); self.assertEqual(task.status,'pending')

    def test_duplicate_delivery_and_cancelled_run(self):
        task=self.task(); claim=remote.claim('a'*32,True)[0]
        remote.complete(task.pk,claim['token'],self.payload())
        remote.complete(task.pk,claim['token'],{'status':404,'html':'','final_url':self.url})
        task.refresh_from_db(); self.assertEqual(task.payload['status'],200)
        self.run.status='cancelled';self.run.save()
        with self.assertRaises(ValueError): remote.complete(task.pk,claim['token'],self.payload())

    def test_expired_and_wrong_generation_results_rejected(self):
        task=self.task(); claim=remote.claim('a'*32,True)[0]
        with self.assertRaises(ValueError): remote.complete(task.pk,'wrong',self.payload())
        self.run.lease='new-generation';self.run.save()
        with self.assertRaises(ValueError): remote.complete(task.pk,claim['token'],self.payload())

    def test_wait_resume_preserves_deadline(self):
        deadline=timezone.now()+timedelta(hours=4)
        self.run.status='waiting_session';self.run.wait_until=deadline;self.run.save()
        remote.claim('a'*32,True)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status,'queued');self.assertEqual(self.run.wait_until,deadline)

    def test_host_validation(self):
        self.assertTrue(remote.allowed_url(self.url))
        for url in ['https://tara.ru.evil.test/','https://evil@tara.ru/','http://tara.ru/','https://tara.ru:123/']:
            self.assertFalse(remote.allowed_url(url))

    def test_redirect_result_rejected(self):
        task=self.task(); claim=remote.claim('a'*32,True)[0]
        with self.assertRaises(ValueError):
            remote.complete(task.pk,claim['token'],{**self.payload(),'final_url':'https://tara.ru/'})

    def test_transport_roundtrip_clears_html_after_consumption(self):
        remote.claim('a'*32,True,pull=False)
        def deliver(_):
            task=remote.claim('a'*32,True)[0]
            remote.complete(task['id'],task['token'],self.payload())
        with patch.object(remote.time,'sleep',side_effect=deliver):
            payload=remote.fetch(self.url)
        self.assertEqual(payload['status'],200)
        task=TaraFetch.objects.get()
        self.assertEqual(task.status,'expired');self.assertEqual(task.payload,{})

    @override_settings(TARA_WORKER_KEY='test-worker-key')
    def test_api_rejects_missing_key_and_accepts_dedicated_key(self):
        from rest_framework.test import APIRequestFactory
        from datasets.api.tara_worker_views import TaraWorkerClaimView
        factory=APIRequestFactory()
        request=factory.post('/worker/claim/',{'owner':'a'*32,'ready':True,'pull':False},format='json')
        self.assertEqual(TaraWorkerClaimView.as_view()(request).status_code,403)
        request=factory.post('/worker/claim/',{'owner':'a'*32,'ready':True,'pull':False},format='json',HTTP_X_TARA_WORKER_KEY='test-worker-key')
        self.assertEqual(TaraWorkerClaimView.as_view()(request).status_code,200)

    def test_disconnected_executor_is_not_available(self):
        remote.claim('a'*32,True,pull=False)
        TaraWorker.objects.update(heartbeat=timezone.now()-timedelta(seconds=91))
        self.assertFalse(remote.available())

    def test_404_is_delivered_not_reclassified_as_block(self):
        task=self.task();claim=remote.claim('a'*32,True)[0]
        remote.complete(task.pk,claim['token'],{'status':404,'html':'missing','final_url':self.url})
        task.refresh_from_db()
        self.assertFalse(task.payload['blocked']);self.assertEqual(task.payload['status'],404)
