import os
import requests

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


def get_bitrix_dialog_id() -> str | None:
    user_id = os.getenv("BITRIX_NOTIFY_USER_ID")

    if not user_id:
        return None

    user_id = str(user_id).strip()

    if user_id.startswith("user") or user_id.startswith("chat"):
        return user_id

    if user_id.isdigit():
        return f"user{user_id}"

    return user_id


def send_bitrix_chat_message(message: str) -> bool:
    enabled = os.getenv("ENABLE_BITRIX_NOTIFICATIONS", "false").lower() == "true"

    if not enabled:
        print("Bitrix notification skipped: ENABLE_BITRIX_NOTIFICATIONS=false")
        return False

    webhook_url = os.getenv("BITRIX_WEBHOOK_URL")
    dialog_id = get_bitrix_dialog_id()

    if not webhook_url or not dialog_id:
        print("Bitrix notification skipped: webhook or dialog id is empty")
        return False

    url = webhook_url.rstrip("/") + "/im.message.add.json"

    response = requests.post(
        url,
        json={
            "DIALOG_ID": dialog_id,
            "MESSAGE": message,
        },
        timeout=30,
    )

    response.raise_for_status()
    print("Bitrix chat notification sent")
    return True


def send_bitrix_failure_notification(context):
    task_instance = context.get("task_instance")
    dag = context.get("dag")
    exception = context.get("exception")

    dag_id = dag.dag_id if dag else "unknown"
    task_id = task_instance.task_id if task_instance else "unknown"
    execution_date = context.get("execution_date")
    log_url = task_instance.log_url if task_instance else ""

    message = (
        "[b]Tara parser pipeline FAILED[/b]\n\n"
        f"DAG: {dag_id}\n"
        f"Task: {task_id}\n"
        f"Execution date: {execution_date}\n"
        f"Error: {exception}\n"
        f"Log: {log_url}"
    )

    send_bitrix_chat_message(message)


DEFAULT_ARGS = {
    "owner": "analytics",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=10),
    "on_failure_callback": send_bitrix_failure_notification,
}


with DAG(
    dag_id="tara_parser_pipeline",
    default_args=DEFAULT_ARGS,
    description="Tara parser pipeline: sitemap -> products -> report",
    start_date=datetime(2026, 6, 23),
    schedule_interval="0 4 1 * *",
    catchup=False,
    max_active_runs=1,
    tags=["parser", "tara"],
) as dag:

    load_sitemap = BashOperator(
        task_id="load_tara_sitemap",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_tara_sitemap"
        ),
        execution_timeout=timedelta(hours=1),
    )

    load_products = BashOperator(
        task_id="load_tara_products",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_tara_products --workers 3"
        ),
        execution_timeout=timedelta(hours=20),
    )

    report_result = BashOperator(
        task_id="report_tara_parser_result",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py report_tara_parser_result --limit 30"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    load_sitemap >> load_products >> report_result