from datetime import timedelta
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="sales_calculator_dispatcher",
    description="Process queued commercial price rebuilds and recover interrupted launches",
    start_date=pendulum.datetime(2026, 9, 30, tz="Europe/Moscow"),
    schedule="* * * * *", catchup=False, max_active_runs=1,
    default_args={"owner": "analytics", "retries": 0},
    tags=["analytics", "sales", "commercial-price"],
) as dag:
    BashOperator(
        task_id="process_refresh",
        bash_command="docker exec analytics-django python manage.py refresh_sales_calculator",
        execution_timeout=timedelta(hours=2),
    )
