"""Select Market website only; competitor parsers are launched separately."""
from datetime import timedelta
import pendulum

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="select_market_base_parser_pipeline",
    default_args={
        "owner": "analytics",
        "depends_on_past": False,
        "retries": 6,
        "retry_delay": timedelta(minutes=10),
    },
    description="Select Market website: YML -> prices/properties -> report",
    start_date=pendulum.datetime(2026, 10, 1, tz="Europe/Moscow"),
    schedule_interval="40 3 * * *",
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=["parser", "base", "select-market"],
) as dag:
    load_products = BashOperator(
        task_id="load_base_products",
        bash_command=(
            "docker exec analytics-django python manage.py "
            "load_base_products --organization select-market"
        ),
        execution_timeout=timedelta(hours=2),
    )
    report_result = BashOperator(
        task_id="report_base_parser_result",
        bash_command=(
            "docker exec analytics-django python manage.py "
            "report_base_parser_result --organization select-market "
            "--limit 30 --skip-bitrix"
        ),
        execution_timeout=timedelta(minutes=15),
    )
    load_products >> report_result
