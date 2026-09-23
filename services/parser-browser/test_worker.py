import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
import worker


class WorkerTests(unittest.TestCase):
    def test_transient_failure_retries_then_succeeds(self):
        failed = {'status':503, 'blocked':False, 'error':'network', 'reason':'ReadTimeout'}
        ok = {'status':200, 'blocked':False, 'error':None}
        with patch.object(worker, 'get_page', side_effect=[failed, ok]) as fetch, patch.object(worker.asyncio, 'sleep', new_callable=AsyncMock):
            result = asyncio.run(worker.fetch_with_retries({'id':1,'url':'https://tara.ru/'}, [], {}))
        self.assertEqual(result['status'], 200)
        self.assertEqual(fetch.call_count, 2)

    def test_network_retries_are_bounded(self):
        with patch.object(worker, 'get_page', side_effect=lambda *args: {'status':503,'blocked':False,'error':'network'}) as fetch, patch.object(worker.asyncio, 'sleep', new_callable=AsyncMock):
            result = asyncio.run(worker.fetch_with_retries({'id':1,'url':'https://tara.ru/'}, [], {}))
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(result['error'], 'request_exhausted')
        self.assertFalse(worker.batch_network_failure([result, {'status':200,'blocked':False}, {'status':200,'blocked':False}]))
        self.assertTrue(worker.batch_network_failure([result, result]))

    def test_missing_and_blocked_pages_are_not_network_retried(self):
        for status, blocked in [(404,False), (401,True), (502,True)]:
            with patch.object(worker, 'get_page', return_value={'status':status,'blocked':blocked,'error':None}) as fetch:
                asyncio.run(worker.fetch_with_retries({'id':1,'url':'https://tara.ru/'}, [], {}))
            self.assertEqual(fetch.call_count, 1)

    def test_url_scope(self):
        self.assertTrue(worker.allowed('https://moskva.tara.ru/catalog/a/?oid=1'))
        for url in ['http://tara.ru/', 'https://tara.ru.evil.test/', 'https://u@tara.ru/', 'https://tara.ru:123/']:
            self.assertFalse(worker.allowed(url))

    def test_outbox_survives_network_loss_then_acknowledges_once(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(worker, 'OUTBOX', Path(directory)):
            worker.spool({'id':1,'token':'lease'}, {'status':404,'html':'','final_url':'https://tara.ru/'})
            with patch.object(worker,'api',side_effect=worker.requests.ConnectionError):
                with self.assertRaises(worker.requests.ConnectionError): asyncio.run(worker.flush())
            self.assertEqual(len(list(Path(directory).glob('*.json'))),1)
            with patch.object(worker,'api',return_value={'accepted':True}) as api:
                asyncio.run(worker.flush());asyncio.run(worker.flush())
                self.assertEqual(api.call_count,1)
            self.assertEqual(list(Path(directory).glob('*.json')),[])

    def test_outbox_is_bound_to_api_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(worker, 'OUTBOX', Path(directory)):
            worker.spool({'id':1,'token':'lease'}, {'status':200,'html':'product'})
            with patch.object(worker,'BASE','https://different.test/api'),patch.object(worker,'api') as api:
                asyncio.run(worker.flush());api.assert_not_called()
            self.assertEqual(len(list(Path(directory).glob('*.json'))),1)

    def test_404_does_not_trigger_recovery_even_with_forbidden_text(self):
        response=Mock(status_code=404,encoding='utf-8')
        response.iter_content.return_value=[b'Forbidden: page removed']
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        client=Mock();client.get.return_value=response
        client.__enter__=Mock(return_value=client);client.__exit__=Mock(return_value=False)
        with patch.object(worker.requests,'Session',return_value=client):
            result=worker.get_page({'url':'https://tara.ru/catalog/a/'},[],{})
        self.assertFalse(result['blocked']);self.assertEqual(result['status'],404)


if __name__ == '__main__':
    unittest.main()
