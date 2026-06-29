from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime


with DAG(
    dag_id="product_url_control_export",
    description=(
        "Build parser product URL control Excel export. "
        "Download URL: /api/v1/datasets/parsers/product-url-control/export/"
    ),
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["parsers", "export", "manual"],
) as dag:

    build_export = BashOperator(
        task_id="build_product_url_control_export",
        bash_command=(
            "docker exec analytics-django "
            "python manage.py build_product_url_control_export"
        ),
    )