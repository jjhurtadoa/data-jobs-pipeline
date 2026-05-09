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
- Deduplication will be implemented in ingestion/staging using a deterministic `source_row_hash`.
- The hash input will include discriminating fields such as `job_title`, `company_name`, `job_posted_date`, `job_location`, `job_via`, and `search_location`.
- This preserves raw fidelity while keeping ingestion idempotent.

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

Phase 2 will implement ingestion logic and hash-based idempotency (without changing the Phase 1 infrastructure baseline).
