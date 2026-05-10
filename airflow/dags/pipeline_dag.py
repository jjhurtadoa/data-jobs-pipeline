from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


default_args = {
	"owner": "data-engineering",
	"depends_on_past": False,
	"retries": 1,
	"retry_delay": timedelta(minutes=5),
}


with DAG(
	dag_id="data_jobs_pipeline",
	default_args=default_args,
	description="Ingest raw jobs CSV, then run dbt models and tests",
	schedule="0 3 * * *",
	start_date=datetime(2026, 1, 1),
	catchup=False,
	max_active_runs=1,
	tags=["data-jobs", "etl", "dbt"],
) as dag:
	ingest_raw_jobs = BashOperator(
		task_id="ingest_raw_jobs",
		bash_command="cd /opt/airflow/project && python -m ingestion.ingest",
		env={
			"DB_HOST": "postgres_pipeline",
			"DB_PORT": "5432",
			"DB_NAME": "jobs_db",
			"DB_USER": "postgres",
			"DB_PASSWORD": "postgres",
			"CSV_PATH": "data/data_jobs.csv",
			"LOG_LEVEL": "INFO",
		},
	)

	dbt_run_models = BashOperator(
		task_id="dbt_run_models",
		bash_command="cd /opt/airflow/project/dbt && python -m dbt.cli.main run --fail-fast",
		env={
			"DBT_PROFILES_DIR": "/opt/airflow/dbt_profiles",
		},append_env=True,
	)

	dbt_run_tests = BashOperator(
		task_id="dbt_run_tests",
		bash_command="cd /opt/airflow/project/dbt && python -m dbt.cli.main test --fail-fast",
		env={
			"DBT_PROFILES_DIR": "/opt/airflow/dbt_profiles",
		},append_env=True,
	)

	ingest_raw_jobs >> dbt_run_models >> dbt_run_tests
