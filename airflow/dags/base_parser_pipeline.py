import os
import requests

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


def send_bitrix_failure_notification(context):
    enabled = os.getenv("ENABLE_BITRIX_NOTIFICATIONS", "false").lower() == "true"

    if not enabled:
        print("Bitrix notification skipped: ENABLE_BITRIX_NOTIFICATIONS=false")
        return

    webhook_url = os.getenv("BITRIX_WEBHOOK_URL")
    user_id = os.getenv("BITRIX_NOTIFY_USER_ID")

    if not webhook_url or not user_id:
        print("Bitrix notification skipped: webhook or user id is empty")
        return

    task_instance = context.get("task_instance")
    dag = context.get("dag")
    exception = context.get("exception")

    dag_id = dag.dag_id if dag else "unknown"
    task_id = task_instance.task_id if task_instance else "unknown"
    execution_date = context.get("execution_date")
    log_url = task_instance.log_url if task_instance else ""

    message = (
        "Base parser pipeline FAILED\n\n"
        f"DAG: {dag_id}\n"
        f"Task: {task_id}\n"
        f"Execution date: {execution_date}\n"
        f"Error: {exception}\n"
        f"Log: {log_url}"
    )

    url = webhook_url.rstrip("/") + "/im.notify.system.add.json"

    response = requests.post(
        url,
        json={
            "USER_ID": user_id,
            "MESSAGE": message,
        },
        timeout=30,
    )

    response.raise_for_status()
    print("Bitrix failure notification sent")


DEFAULT_ARGS = {
    "owner": "analytics",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=10),
    "on_failure_callback": send_bitrix_failure_notification,
}


with DAG(
    dag_id="base_parser_pipeline",
    default_args=DEFAULT_ARGS,
    description="Base parser pipeline: YML/PHP -> prices/properties -> report",
    start_date=datetime(2026, 6, 23),
    schedule_interval="40 0 1 * *",
    catchup=False,
    max_active_runs=1,
    tags=["parser", "base"],
) as dag:

    load_products = BashOperator(
        task_id="load_base_products",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_base_products"
        ),
        execution_timeout=timedelta(hours=2),
    )

    report_result = BashOperator(
        task_id="report_base_parser_result",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py report_base_parser_result --limit 30"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    load_products >> report_result