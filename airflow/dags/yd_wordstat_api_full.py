import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLE_EXTERNAL_API_LOADS = (
    os.getenv("ENABLE_EXTERNAL_API_LOADS", "false").lower() == "true"
)


with DAG(
    dag_id="yd_wordstat_api_full",
    start_date=datetime(2026, 1, 1),
    schedule="0 13 3 * *",
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=["analytics", "wordstat", "external_api"],
) as dag:

    disabled = EmptyOperator(
        task_id="disabled_external_api_loads",
    )

    if ENABLE_EXTERNAL_API_LOADS:
        load_yd_wordstat = BashOperator(
            task_id="load_yd_wordstat_from_api",
            bash_command="docker exec analytics-django python manage.py load_yd_wordstat_api",
            execution_timeout=timedelta(days=10),
            retries=0,
        )
