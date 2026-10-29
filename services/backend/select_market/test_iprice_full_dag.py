"""Exercise the sensor without importing/starting an Airflow installation."""
import ast
import logging
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
import requests


class FullDagTests(TestCase):
    def sensor(self):
        path = Path(__file__).resolve().parents[3] / 'airflow/dags/select_market_competitors_full.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        compile(tree, str(path), 'exec')
        definition = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        namespace = {'BaseSensorOperator': type('Sensor', (), {'log': logging.getLogger(__name__)}),
                     'requests': requests, 'os': os, 'AirflowException': RuntimeError}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), namespace)
        return namespace['SelectMarketCompetitorsSensor']()

    def test_waiting_does_not_fail_and_reuses_request_identity(self):
        sensor = self.sensor()
        context = {'run_id': 'manual__2026-10-29T00:00:00Z'}
        with patch.object(requests, 'post') as post:
            for status in (409, 503):
                post.return_value = Mock(status_code=status)
                self.assertFalse(sensor.poke(context))
            for state in ('queued', 'running', 'waiting_session', 'waiting_tara', 'success'):
                post.return_value = Mock(status_code=200)
                post.return_value.json.return_value = {'id': 1, 'status': state, 'step': 'tara_parser', 'results': {}}
                self.assertEqual(sensor.poke(context), state == 'success')
            self.assertTrue(all(call.kwargs['json'] == {'request_key': context['run_id']} for call in post.call_args_list))
            self.assertTrue(all('/select-market/' in call.args[0] for call in post.call_args_list))
        with patch.object(requests, 'post', side_effect=requests.Timeout):
            self.assertFalse(sensor.poke(context))

    def test_terminal_source_error_is_not_reported_as_success(self):
        sensor = self.sensor()
        with patch.object(requests, 'post') as post:
            for state in ('failed', 'cancelled'):
                post.return_value = Mock(status_code=200)
                post.return_value.json.return_value = {'id': 1, 'status': state, 'step': 'tt_parser', 'results': {}, 'error': 'Source failed'}
                with self.assertRaisesRegex(RuntimeError, 'Source failed'):
                    sensor.poke({'run_id': 'same'})
