from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="onec_document_management_reminder_monthly",
    description="Monthly Bitrix reminder to sign in to 1C Document Management",
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Moscow"),
    schedule="2 8 1 * *",
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "analytics", "retries": 0},
    tags=["analytics", "1c", "reminder", "bitrix24"],
) as dag:
    BashOperator(
        task_id="send_login_reminder",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py remind_onec_document_management_login"
        ),
        execution_timeout=timedelta(minutes=2),
    )
