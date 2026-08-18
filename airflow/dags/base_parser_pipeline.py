from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


DEFAULT_ARGS = {
    "owner": "analytics",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=10),
}


with DAG(
    dag_id="base_parser_pipeline",
    default_args=DEFAULT_ARGS,
    description="Base parser pipeline: YML/PHP -> prices/properties -> report",
    start_date=datetime(2026, 6, 1),
    schedule_interval="40 0 * * *",
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
            "python manage.py report_base_parser_result "
            "--limit 30 --skip-bitrix"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    load_products >> report_result
