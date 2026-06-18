import os
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


with DAG(
    dag_id="table_health_daily",
    start_date=datetime(2026, 1, 1),
    schedule="4 8 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    tags=["analytics", "maintenance", "health"],
) as dag:

    check_table_health = BashOperator(
        task_id="check_table_health",
        bash_command="""
        curl -f -X POST http://django:8000/api/v1/datasets/maintenance/table-health/ \
          -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
          -H "Content-Type: application/json"
        """,
        env={
            "INTERNAL_API_KEY": INTERNAL_API_KEY,
        },
    )