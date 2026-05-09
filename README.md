# Data Jobs Pipeline

This repository contains the implementation for a Data Engineering technical assessment.

## Scope Completed So Far

Phase 0 and Phase 1 are prepared:
- Project scaffold and repository structure.
- Local infrastructure with Docker Compose.
- Raw database schema for CSV ingestion.

## Phase 1 Architecture

### Services

The local stack uses three services in `docker-compose.yml`:

1. `postgres_pipeline`
- Main transactional store for pipeline data.
- Hosts raw and analytics schemas.

2. `postgres_airflow`
- Dedicated metadata database for Airflow.
- Isolated from business data to avoid cross-impact.

3. `pgadmin`
- Local UI for inspection and manual troubleshooting.

### Why Two PostgreSQL Instances

Using separate PostgreSQL instances provides:
- Better isolation between orchestration metadata and pipeline data.
- Lower risk of accidental changes across domains.
- Cleaner operations for backup, restore, and incident diagnosis.

## Raw Schema Design

The raw layer is created in `schema/schema.sql`:
- `raw` schema as landing zone.
- `raw.jobs` table with source-aligned columns.
- `job_skills` and `job_type_skills` stored as `JSONB` to preserve semi-structured content from the CSV.
- `analytics` schema created as destination for future 3NF models.

### Deduplication Strategy

The raw layer preserves source records as-is.

Phase 2 approach:
- Idempotency is controlled at file level using a deterministic `MD5` fingerprint.
- Execution metadata is stored in `raw.ingestion_log`.
- If a completed `file_md5` already exists, ingestion is skipped.
- `raw.jobs` stores only raw CSV data columns.

Known trade-offs:
- `job_posted_date` is intentionally kept as `TEXT` in raw; parsing and normalization will be handled in later stages.

## Environment Configuration

The project includes:
- `.env.example` with all required variables.
- `.env` for local execution.

Current environment groups:
- Pipeline PostgreSQL variables.
- Airflow PostgreSQL variables.
- pgAdmin variables.
- App-level variables for ingestion.

## How To Run Phase 1

Run from repository root:

```bash
docker compose up -d postgres_pipeline postgres_airflow pgadmin
docker compose ps
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -f /schema/schema.sql
```

## Validation Checklist

### 1) Services status

```bash
docker compose ps
```

Expected:
- `postgres_pipeline` is running and healthy.
- `postgres_airflow` is running and healthy.
- `pgadmin` is running.

### 2) Schemas created

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "\dn"
```

Expected schemas:
- `raw`
- `analytics`
- `public`

### 3) Raw table exists

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "\dt raw.*"
```

Expected table:
- `raw.jobs`

### 4) Table structure

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "\d raw.jobs"
```

Expected highlights:
- `job_skills` is `jsonb`
- `job_type_skills` is `jsonb`

### 5) pgAdmin endpoint

PowerShell:

```powershell
Invoke-WebRequest -Uri "http://localhost:5050" -UseBasicParsing | Select-Object StatusCode, StatusDescription
```

Expected:
- `200 OK`

## Next Step

Phase 3 will focus on relational modeling (3NF), transformations, and data quality checks.

## Phase 2 Ingestion (Implemented)

The ingestion module now reads `data/data_jobs.csv`, parses semi-structured fields, and loads into `raw.jobs`.

The ingestion summary log now separates semi-structured profiling into:
- `job_skills_missing`
- `job_skills_invalid`
- `job_type_skills_missing`
- `job_type_skills_invalid`

`parse_warnings` counts only invalid (malformed) semi-structured values.

Idempotency strategy:
- A file-level fingerprint (`MD5`) is computed before loading.
- File execution history is stored in `raw.ingestion_log` (pipeline metadata only).
- If a completed fingerprint already exists for that file, ingestion is skipped entirely.
- `raw.jobs` stores only source CSV data — no pipeline metadata columns.
- Re-running ingestion on an already-loaded file is safe and produces no duplicate rows.

Implemented components:
- `ingestion/parsers.py`: parsing and normalization utilities.
- `ingestion/db.py`: PostgreSQL connection and batch insert helpers.
- `ingestion/ingest.py`: ingestion flow and CLI/module entrypoint.
- `ingestion/logging_config.py`: logging bootstrap.
- `tests/test_parsers.py` and `tests/test_ingest.py`: unit tests.

### Run tests

```bash
pytest -q
```

### Run ingestion

```bash
python -m ingestion.ingest
```

Optional smoke run with limited rows:

```bash
INGEST_MAX_ROWS=500 python -m ingestion.ingest
```

PowerShell equivalent:

```powershell
$env:INGEST_MAX_ROWS=500
python -m ingestion.ingest
```

Run full ingestion:

```powershell
Remove-Item Env:INGEST_MAX_ROWS -ErrorAction SilentlyContinue
python -m ingestion.ingest
```

### Validate loaded data

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT count(*) FROM raw.jobs;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT id, job_skills, job_type_skills FROM raw.jobs WHERE job_skills IS NOT NULL OR job_type_skills IS NOT NULL LIMIT 5;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT file_md5, source_name, status, total_rows, inserted_rows, parse_warnings, job_skills_missing, job_skills_invalid, job_type_skills_missing, job_type_skills_invalid, finished_at FROM raw.ingestion_log ORDER BY finished_at DESC LIMIT 10;"
```
