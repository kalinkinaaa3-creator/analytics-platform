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
    dag_id="nomenclature_stock_api_daily",
    description="Nomenclature stocks load from 1C API at minutes 04 and 34 every hour",
    start_date=datetime(2026, 1, 1),
    schedule="4,34 * * * *",
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=[
        "analytics",
        "nomenclature_stock",
        "external_api",
    ],
) as dag:

    if ENABLE_EXTERNAL_API_LOADS:
        load_stocks = BashOperator(
            task_id="load_nomenclature_stocks_from_api",
            bash_command="""
            curl -f -X POST \
              http://django:8000/api/v1/datasets/nomenclature-stock/load-from-api/ \
              -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
              -H "Content-Type: application/json"
            """,
            env={
                "INTERNAL_API_KEY": INTERNAL_API_KEY,
            },
            execution_timeout=timedelta(hours=2),
        )
    else:
        disabled = EmptyOperator(task_id="disabled_external_api_loads")
