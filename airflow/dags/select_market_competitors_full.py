"""Manual full catalogue refresh, isolated to Select Market. TT -> PS -> Tara."""
import os
from datetime import datetime, timedelta
import requests
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.sensors.base import BaseSensorOperator


class SelectMarketCompetitorsSensor(BaseSensorOperator):
    def poke(self, context):
        try:
            response = requests.post(
                'http://django:8000/api/v1/select-market/iprice/parsers/full/internal/run/',
                headers={'X-Internal-Api-Key': os.getenv('INTERNAL_API_KEY', '')},
                json={'request_key': context['run_id']}, timeout=30,
            )
        except (requests.ConnectionError, requests.Timeout):
            self.log.warning('Select Market status temporarily unavailable; waiting')
            return False
        if response.status_code == 409 or response.status_code >= 500:
            return False
        response.raise_for_status()
        run = response.json()
        self.log.info('Select Market full run #%s: %s; step=%s; results=%s',
                      run['id'], run['status'], run['step'], run['results'])
        if run['status'] in ('failed', 'cancelled'):
            raise AirflowException(run.get('error') or 'Select Market collection stopped')
        return run['status'] == 'success'


with DAG(
    dag_id='select_market_competitors_full', schedule=None, catchup=False,
    start_date=datetime(2026, 10, 28), max_active_runs=1, is_paused_upon_creation=True,
    description='Manual Select Market full collection: TOPAZ -> PLASTIC SYSTEM -> TARA',
    default_args={'owner': 'analytics', 'retries': 0}, tags=['parser', 'select-market', 'full'],
) as dag:
    collect_competitors = SelectMarketCompetitorsSensor(
        task_id='tt_then_ps_then_tara', mode='reschedule', poke_interval=60,
        timeout=7 * 24 * 3600, execution_timeout=timedelta(minutes=2),
    )
