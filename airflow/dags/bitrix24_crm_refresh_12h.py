from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="bitrix24_crm_refresh_12h",
    description="Refresh Bitrix24 CRM analytics every 12 hours",
    start_date=datetime(2026, 1, 1),
    schedule="10 3,15 * * 1-6",
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "analytics", "retries": 5},
    tags=["analytics", "bitrix24", "crm"],
) as dag:
    BashOperator(
        task_id="refresh_bitrix24_crm",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py refresh_bitrix24"
        ),
        execution_timeout=timedelta(hours=3),
    )
