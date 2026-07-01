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
    dag_id="tt_parser_pipeline",
    default_args=DEFAULT_ARGS,
    description="TT parser pipeline: links -> products -> report",
    start_date=datetime(2026, 6, 1),
    schedule_interval="0 1 1 * *",
    catchup=False,
    max_active_runs=1,
    tags=["parser", "tt"],
) as dag:

    load_links = BashOperator(
        task_id="load_tt_links",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_tt_links"
        ),
        execution_timeout=timedelta(hours=3),
    )

    load_products = BashOperator(
        task_id="load_tt_products",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py load_tt_products --workers 3"
        ),
        execution_timeout=timedelta(hours=14),
    )

    report_result = BashOperator(
        task_id="report_tt_parser_result",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py report_tt_parser_result --limit 30"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    load_links >> load_products >> report_result