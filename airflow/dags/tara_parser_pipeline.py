import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.sensors.base import BaseSensorOperator


class TaraRunSensor(BaseSensorOperator):
    """Create once, observe durable execution; also supports repeated session waits."""
    def poke(self, context):
        try:
            response = requests.post(
                "http://django:8000/api/v1/datasets/parsers/tara/internal/run/",
                headers={"X-Internal-Api-Key": os.getenv("INTERNAL_API_KEY", "")},
                json={"request_key": context["run_id"]}, timeout=30,
            )
        except (requests.ConnectionError, requests.Timeout):
            self.log.warning("Tara status is temporarily unavailable; retrying at next poke")
            return False
        if response.status_code >= 500:
            return False
        if response.status_code == 409:
            return False
        response.raise_for_status()
        run = response.json()
        self.log.info("Tara run %s: %s; counts=%s", run["id"], run["status"], run["counts"])
        if run["status"] in ("failed", "cancelled"):
            raise AirflowException(run.get("error") or "Tara run stopped")
        return run["status"] == "success"


with DAG(
    dag_id="tara_parser_pipeline", start_date=datetime(2026, 6, 1),
    schedule=None, catchup=False, max_active_runs=1,
    default_args={"owner": "analytics", "retries": 0},
    tags=["parser", "tara"],
) as dag:
    load_tara = TaraRunSensor(
        task_id="load_tara", mode="reschedule", poke_interval=60,
        # Four-hour session deadlines are enforced separately per waiting episode.
        timeout=7 * 24 * 3600, execution_timeout=timedelta(minutes=2),
    )
