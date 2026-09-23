import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import worker


class WorkerTests(unittest.TestCase):
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
