import os
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


ENABLE_EXTERNAL_API_LOADS = os.getenv("ENABLE_EXTERNAL_API_LOADS", "false").lower() == "true"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


with DAG(
    dag_id="planned_sales_api_daily",
    start_date=datetime(2026, 1, 1),
    schedule="30 7 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    tags=["analytics", "planned_sales", "external_api"],
) as dag:

    disabled = EmptyOperator(
        task_id="disabled_external_api_loads",
    )

    load_planned_sales = BashOperator(
        task_id="load_planned_sales_from_api",
        bash_command="""
        curl -f -X POST http://django:8000/api/v1/datasets/planned-sales/load-from-api/ \
          -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
          -H "Content-Type: application/json"
        """,
        env={
            "INTERNAL_API_KEY": INTERNAL_API_KEY,
        },
    )

    if ENABLE_EXTERNAL_API_LOADS:
        load_planned_sales
    else:
        disabled