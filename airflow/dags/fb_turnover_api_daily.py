import os
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLE_EXTERNAL_API_LOADS = os.getenv("ENABLE_EXTERNAL_API_LOADS", "false").lower() == "true"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


with DAG(
    dag_id="fb_turnover_api_daily",
    start_date=datetime(2026, 1, 1),
    schedule="10 6 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    tags=["analytics", "turnover", "external_api"],
) as dag:

    disabled = EmptyOperator(
        task_id="disabled_external_api_loads",
    )

    load_fb_turnover = BashOperator(
        task_id="load_fb_turnover_from_api",
        bash_command="""
        curl -f -X POST http://django:8000/api/v1/datasets/fb-turnover/load-from-api/ \
          -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
          -H "Content-Type: application/json"
        """,
        env={
            "INTERNAL_API_KEY": INTERNAL_API_KEY,
        },
    )

    if ENABLE_EXTERNAL_API_LOADS:
        load_fb_turnover
    else:
        disabled