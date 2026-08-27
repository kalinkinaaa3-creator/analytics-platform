from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator


MOSCOW_TZ = pendulum.timezone("Europe/Moscow")


with DAG(
    dag_id="bitrix24_recent_leads_reconciliation_weekly",
    description="Reconcile the previous 14 complete Moscow calendar days of CRM leads",
    start_date=pendulum.datetime(2026, 1, 4, tz=MOSCOW_TZ),
    schedule="00 10 * * 0",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "analytics",
        "retries": 5,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["analytics", "bitrix24", "crm", "reconciliation"],
) as dag:
    BashOperator(
        task_id="reconcile_recent_bitrix24_leads",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py reconcile_bitrix24_recent_leads --days 14"
        ),
        execution_timeout=timedelta(hours=3),
    )
