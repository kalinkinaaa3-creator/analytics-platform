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
    dag_id="ps_parser_pipeline",
    default_args=DEFAULT_ARGS,
    description="PS parser pipeline: links -> products -> report",
    start_date=datetime(2026, 6, 1),
    schedule_interval="0 2 1 * *",
    catchup=False,
    max_active_runs=1,
    tags=["parser", "ps"],
) as dag:

    load_links = BashOperator(
        task_id="load_ps_links",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_ps_links"
        ),
        execution_timeout=timedelta(hours=2),
    )

    load_products = BashOperator(
        task_id="load_ps_products",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_ps_products --workers 3"
        ),
        execution_timeout=timedelta(hours=14),
    )

    report_result = BashOperator(
        task_id="report_ps_parser_result",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py report_ps_parser_result --limit 30"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    load_links >> load_products >> report_result