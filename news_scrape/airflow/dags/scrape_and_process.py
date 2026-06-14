import asyncio
from datetime import timedelta

from scripts.fetch_data import (
    fetch_new_data,
    process_mentions_data,
)

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


def run_fetch_news(**_):
    asyncio.run(fetch_new_data())


def run_process_mentions(**kwargs):
    execution_date = kwargs["execution_date"]
    _ = asyncio.run(process_mentions_data(execution_date))


default_args = {
    "owner": "airflow",
    "start_date": days_ago(1),
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="scrape_and_process_dag",
    default_args=default_args,
    schedule_interval="0 */1 * * *",  # every 1 hour
    catchup=False,
    tags=["news", "ner"],
) as dag:
    fetch_news = PythonOperator(
        task_id="fetch_news",
        python_callable=run_fetch_news,
    )

    process_mentions_task = PythonOperator(
        task_id="process_mentions",
        python_callable=run_process_mentions,
        provide_context=True,
    )

    fetch_news >> process_mentions_task
