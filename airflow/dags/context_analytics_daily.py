import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLED = os.getenv("ENABLE_CONTEXT_ANALYTICS_LOADS", "false").lower() == "true"

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
    if ENABLED:
        refresh = BashOperator(
            task_id="rebuild_from_max_date_with_14_day_overlap",
            bash_command="docker exec analytics-django python manage.py refresh_context_analytics --trigger scheduled",
            execution_timeout=timedelta(hours=4),
            retries=2,
            retry_delay=timedelta(minutes=10),
        )
    else:
        disabled = EmptyOperator(task_id="disabled_external_api_loads")
