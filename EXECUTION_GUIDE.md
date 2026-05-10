# Execution Guide: Data Jobs Pipeline

This file is a practical runbook. The README is the source of truth for architecture, design decisions, and the OLAP next step.

## Prerequisites

- Docker Desktop running
- Git
- Python 3.11
- PostgreSQL client, if you want to run manual SQL checks

## 1. Bring Up Infrastructure

```bash
docker compose up -d postgres_pipeline postgres_airflow pgadmin
docker compose ps
```

Expected services:
- `postgres_pipeline`
- `postgres_airflow`
- `pgadmin`

## 2. Initialize PostgreSQL Schemas

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -f schema/schema.sql
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "\dn"
```

Expected schemas:
- `raw`
- `analytics`
- `public`

## 3. Run Ingestion

Local run:

```bash
python -m ingestion.ingest
```

Smoke run:

```bash
INGEST_MAX_ROWS=500 python -m ingestion.ingest
```

PowerShell:

```powershell
$env:INGEST_MAX_ROWS=500
python -m ingestion.ingest
```

Validate raw data:

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM raw.jobs;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT file_md5, status, total_rows, inserted_rows, parse_warnings FROM raw.ingestion_log ORDER BY finished_at DESC LIMIT 5;"
```

## 4. Run dbt

```bash
cd dbt
dbt debug
dbt build
```

Tests only:

```bash
dbt test
```

Docs:

```bash
dbt docs generate
dbt docs serve
```

## 5. Run Airflow

```bash
docker compose up -d airflow-init
docker compose up -d airflow-scheduler airflow-webserver
docker compose ps
```

Manual DAG run:

```bash
docker compose exec airflow-webserver airflow dags test data_jobs_pipeline 2026-05-10
```

Optional logs:

```bash
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-webserver
```

## 6. Validate The Model

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM core.job_posting;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM marts.job_skill;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM raw.jobs;"
```

## 7. Run Tests

Unit tests:

```bash
pytest tests/test_parsers.py tests/test_ingest.py -v
```

DAG tests:

```bash
pytest tests/test_dag.py -v
```

If Airflow is not installed on the host, run the DAG tests inside the Airflow container:

```bash
docker compose exec airflow-webserver bash -c "cd /opt/airflow/project && pytest tests/test_dag.py -v"
```

## 8. Troubleshooting

- If ingestion cannot connect, use `DB_HOST=localhost` outside containers and `DB_HOST=postgres_pipeline` inside Docker.
- If dbt fails, confirm `schema/schema.sql` was applied and `dbt debug` passes.
- If Airflow fails, confirm `airflow-init` completed before starting scheduler and webserver.

## 9. Relationship To README

This guide is a short execution checklist. The README contains the detailed explanation of ingestion, 3NF modeling, orchestration, CI/CD, and the OLAP next step.
