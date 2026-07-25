import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLE_EXTERNAL_API_LOADS = (
    os.getenv("ENABLE_EXTERNAL_API_LOADS", "false").lower() == "true"
)

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


with DAG(
    dag_id="nomenclature_price_api_daily",
    description="Daily nomenclature prices load from 1C API",
    start_date=datetime(2026, 1, 1),
    schedule="20 1 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=[
        "analytics",
        "nomenclature_price",
        "external_api",
    ],
) as dag:

    disabled = EmptyOperator(
        task_id="disabled_external_api_loads",
    )

    load_prices = BashOperator(
        task_id="load_nomenclature_prices_from_api",
        bash_command="""
        curl -f -X POST \
          http://django:8000/api/v1/datasets/nomenclature-price/load-from-api/ \
          -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
          -H "Content-Type: application/json"
        """,
        env={
            "INTERNAL_API_KEY": INTERNAL_API_KEY,
        },
        execution_timeout=timedelta(hours=2),
    )

    if ENABLE_EXTERNAL_API_LOADS:
        load_prices
    else:
        disabled