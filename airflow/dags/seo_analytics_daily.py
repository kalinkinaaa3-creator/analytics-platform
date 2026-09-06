import os
from datetime import timedelta

import pendulum

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLE_SEO_ANALYTICS_LOADS = os.getenv("ENABLE_SEO_ANALYTICS_LOADS", "false").lower() == "true"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


with DAG(
    dag_id="seo_analytics_daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Moscow"),
    schedule="40 6 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=4),
    tags=["analytics", "seo", "yandex_metrika"],
) as dag:
    disabled = EmptyOperator(task_id="disabled_external_api_loads")

    refresh = BashOperator(
        task_id="rebuild_from_max_month_with_previous_month_overlap",
        bash_command="""
        curl --fail --show-error --silent \
          --connect-timeout 10 \
          --max-time 30 \
          -X POST 'http://django:8000/api/v1/seo/refresh/internal/?window=two-months' \
          -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
          -H "Content-Type: application/json"
        """,
        env={"INTERNAL_API_KEY": INTERNAL_API_KEY},
        execution_timeout=timedelta(minutes=2),
        retries=2,
        retry_delay=timedelta(minutes=10),
    )

    if ENABLE_SEO_ANALYTICS_LOADS:
        refresh
    else:
        disabled
