"""Windows executor maintenance. Historical DAG id is kept for Airflow continuity."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id='tara_session_dispatcher', start_date=datetime(2026, 9, 1),
    schedule='* * * * *', catchup=False, max_active_runs=1,
    is_paused_upon_creation=False, tags=['parser', 'tara'],
) as dag:
    dispatch = BashOperator(
        task_id='dispatch',
        bash_command='docker exec analytics-django python manage.py process_tara_jobs',
        execution_timeout=timedelta(minutes=5), retries=0,
    )
