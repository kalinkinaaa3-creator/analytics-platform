import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLED = os.getenv("ENABLE_CONTEXT_ANALYTICS_LOADS", "false").lower() == "true"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

with DAG(
    dag_id="context_analytics_daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Moscow"),
    schedule="50 6 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=4),
    tags=["analytics", "context", "yandex_direct"],
) as dag:
    disabled = EmptyOperator(task_id="disabled_external_api_loads")
    refresh = BashOperator(
        task_id="rebuild_from_max_date_with_14_day_overlap",
        bash_command="""
        curl --fail-with-body --show-error --silent \
          --connect-timeout 10 \
          --max-time 30 \
          -X POST 'http://django:8000/api/v1/context/refresh/internal/' \
          -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
          -H "Content-Type: application/json"
        """,
        env={"INTERNAL_API_KEY": INTERNAL_API_KEY},
        execution_timeout=timedelta(minutes=2),
        retries=2,
        retry_delay=timedelta(minutes=10),
    )
    refresh if ENABLED else disabled
