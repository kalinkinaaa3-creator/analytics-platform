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
    dag_id="tara_parser_pipeline",
    default_args=DEFAULT_ARGS,
    description="Tara parser pipeline: sitemap -> products -> retry failed -> report",
    start_date=datetime(2026, 6, 1),
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
            "python manage.py load_tara_products --workers 5"
        ),
        execution_timeout=timedelta(hours=20),
    )

    retry_failed_products = BashOperator(
        task_id="retry_failed_tara_products",
        bash_command=(
            "sleep 1200 && "
            "docker exec analytics-django "
            "python manage.py load_tara_products "
            "--retry-failed "
            "--workers 5"
        ),
        execution_timeout=timedelta(hours=3),
    )

    report_result = BashOperator(
        task_id="report_tara_parser_result",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py report_tara_parser_result --limit 30"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    load_sitemap >> load_products >> retry_failed_products >> report_result