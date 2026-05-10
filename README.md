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

## Phase 3: Data Modeling in 3NF with dbt (Implemented)

Phase 3 transforms raw job posting data into a **Third Normal Form (3NF)** relational model using dbt.

### Architecture Overview

The model is organized into three layers:

**Staging (`staging/`)**: Parse, normalize, and deduplicate
- `stg_raw_jobs`: Business key-based deduplication with skill aggregation
- `stg_job_skills_exploded`: Explode job_skills array into individual rows
- `stg_job_type_skills_exploded`: Parse job_type_skills dictionary and explode by category

**Core (`core/`)**: Normalized 3NF tables
- **Dimensions**: company, country, platform, schedule_type, job_title_category, salary_rate_type, skill, skill_category
- **Central Entity**: job_posting (with all dimensional FKs)

**Marts (`marts/`)**: Analytical layer
- `job_skill`: M:N bridge resolving job-skill relationships

### Deduplication Strategy

**Problem**: ~200 duplicate job postings with identical content except for skills.

**Solution** (Business Key approach):
1. Compute MD5 hash excluding skill fields
2. For each business key, keep the **first (earliest ingested)** record
3. Aggregate all **unique skills** from all duplicates
4. Result: 785,741 → ~785,700 unique postings

### 3NF Compliance

This design eliminates redundancy while maintaining referential integrity:

| Entity | Rationale |
|--------|-----------|
| `company` | 6,700+ values require normalization |
| `skill` | 5,000+ unique skills deduplicated across sources |
| `job_skill` | Resolves multivalued job_skills attribute (1NF violation) |
| `job_posting` | Central entity; all non-key fields depend only on job_id |

### Setup & Execution

**Install dbt**:
```bash
pip install dbt-postgres
```

**Verify connection**:
```bash
cd dbt
dbt debug
```

**Build all models** (staging → core → marts):
```bash
dbt build
```

**Run tests** (uniqueness, not-null, referential integrity):
```bash
dbt test
```

**Generate documentation**:
```bash
dbt docs generate
dbt docs serve  # Open at localhost:8000
```

### Expected Output

After `dbt build`:

| Layer | Table | Rows | Purpose |
|-------|-------|------|---------|
| Staging | stg_raw_jobs | ~785,700 | Deduplicated base |
| Core | company | ~6,726 | Lookup: companies |
| Core | skill | ~5,000-6,000 | Lookup: skills |
| Core | job_posting | ~785,700 | Central: jobs with FKs |
| Marts | job_skill | ~2-3M | Bridge: job → skills |

### Validation Queries

```sql
-- Check deduplication
SELECT COUNT(DISTINCT business_key) FROM staging.stg_raw_jobs;

-- Check FK integrity
SELECT COUNT(*) FROM core.job_posting WHERE company_id IS NULL;
-- Expected: 0

-- Check bridge deduplication
SELECT job_id, skill_id, skill_cat_id, COUNT(*) as cnt
FROM marts.job_skill
GROUP BY job_id, skill_id, skill_cat_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows
```

### Architecture Decisions

**Why 3NF, not Star Schema?**
- 3NF eliminates redundancy and maintains data integrity at the source
- BI consumers can materialize star schema views on top of 3NF as needed
- Separates analytical data modeling from BI-specific denormalization

**Why Skills Are Separated?**
- `job_skills` (array) and `job_type_skills` (dictionary) have different structures
- Exploding and merging them in staging ensures consistency downstream
- `job_skill` bridge table provides a clean M:N interface

**Why Business Key for Dedup?**
- Deterministic and reproducible across runs
- Survives incremental reloads
- Easier to audit than row-level hashing

**Strict 3NF Policy for Company Dimension**
- `company` is treated as a mandatory dimension for `job_posting`
- Rows with null/blank `company_name` are excluded from `company` and `job_posting`
- Trade-off: a small number of source records can be dropped to preserve non-null PK/FK integrity
- Rationale: prioritizes relational consistency and referential integrity for assessment requirements

**Bridge Consistency Rule (`job_skill` vs `job_posting`)**
- `job_skill` only keeps rows whose `job_id` exists in `job_posting`
- Rationale: avoids orphan records in the M:N bridge when a posting is excluded by 3NF rules
- Implementation note: filtering is enforced in the mart model via inner join to valid posting IDs

### dbt Validation Protocol (Recommended)

Use this sequence after changing models or tests:

```bash
# 1) Rebuild bridge if job posting or skill logic changed
dbt run --select job_skill

# 2) Validate the critical FK relationship explicitly
dbt test --select relationships_job_skill_job_id__job_id__ref_job_posting_

# 3) Build focused dependency graph for company and postings
dbt build --select company job_posting job_skill

# 4) Full regression (optional but recommended before delivery)
dbt build
```

Expected outcome:
- No failing relationship tests between `job_skill.job_id` and `job_posting.job_id`
- No failing reconciliation tests between staging and `job_posting` scope
- No deprecation warning for top-level generic test arguments in `schema.yml`

## Phase 4: Orchestration with Airflow (Implemented)

Phase 4 introduces **Apache Airflow** for automated, scheduled orchestration of the entire ETL pipeline.

### Architecture Overview

The orchestration stack consists of:

**Services** (added to `docker-compose.yml`):
1. `airflow-init`: One-time initialization of Airflow metadata database and default user
2. `airflow-scheduler`: Executes DAGs on schedule and monitors task health
3. `airflow-webserver`: UI for DAG visualization, manual triggers, and monitoring

**DAG Definition** (`airflow/dags/pipeline_dag.py`):
- **DAG ID**: `data_jobs_pipeline`
- **Schedule**: Daily at 03:00 UTC (`0 3 * * *`)
- **Start Date**: 2026-01-01
- **Catchup**: Disabled (prevents backfill storms on deployment)
- **Max Active Runs**: 1 (ensures idempotency, prevents concurrent runs)

### DAG Topology

The DAG implements a **linear 3-stage pipeline**:

```
ingest_raw_jobs
       ↓
dbt_run_models
       ↓
dbt_run_tests
```

| Stage | Task | Operator | Command | Failure Behavior |
|-------|------|----------|---------|------------------|
| Ingest | `ingest_raw_jobs` | BashOperator | `python -m ingestion.ingest` | Fail-fast (stops pipeline) |
| Transform | `dbt_run_models` | BashOperator | `python -m dbt.cli.main run --fail-fast` | Fail-fast (stops pipeline) |
| Validate | `dbt_run_tests` | BashOperator | `python -m dbt.cli.main test --fail-fast` | Fail-fast (stops pipeline) |

### Technical Decisions

**Why BashOperator?**
- Simplicity: direct command execution without Airflow operators overhead
- Maintainability: pipeline logic stays in Python/dbt scripts, not Airflow DAG code
- Portability: bash commands remain testable outside Airflow

**Why Python Module Invocation for dbt?**
- `dbt` binary may not be in PATH inside container
- `python -m dbt.cli.main` is path-independent and works reliably in containerized environments
- Ensures consistent behavior between local and CI contexts

**Why Separate DB for Airflow Metadata?**
- Airflow uses SQLAlchemy ORM with specific schema requirements
- Isolating metadata from business data prevents accidental overwrites
- Enables independent backup/restore of Airflow state

**Environment Variable Handling**
- Ingestion task injects database credentials directly (e.g., `DB_HOST`, `DB_USER`, `DB_PASSWORD`)
- dbt tasks inject `DBT_PROFILES_DIR` to locate the connection profile
- Container-based execution: `load_dotenv(override=False)` in Python code allows Docker Compose environment to take precedence over local `.env` files

### Setup & Execution

**Start the Airflow stack**:
```bash
docker compose up -d airflow-init
# Wait for init to complete (check logs)
docker compose up -d airflow-scheduler airflow-webserver
docker compose ps
```

**Monitor logs** (optional, for debugging):
```bash
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-webserver
```

**Access the UI**:
- URL: `http://localhost:8080`
- Username: `airflow`
- Password: `airflow`

**Manually trigger the DAG** (test run):
```bash
docker compose exec airflow-webserver airflow dags test data_jobs_pipeline 2026-05-10
```

**Expected output**:
- All 3 tasks execute in sequence
- `dbt_run_tests` passes (14/14 assertions)
- Logs show successful ingestion, model materialization, and test validation

### DAG Testing

**Unit tests** (`tests/test_dag.py`):
- Validate DAG structure without running Airflow
- Cover: no import errors, correct task count, proper dependencies, no cycles
- Run inside container (Airflow is Linux-only):

```bash
docker compose exec airflow-webserver bash -c "cd /opt/airflow/project && python -m pytest tests/test_dag.py -v"
```

Expected: 14/14 PASSED

**Integration test** (manual):
```bash
docker compose exec airflow-webserver airflow dags test data_jobs_pipeline <YYYY-MM-DD>
```

### Validation Queries

**Check Airflow database** (metadata):
```bash
docker compose exec postgres_airflow psql -U airflow -d airflow -c "SELECT dag_id, task_id, state, started_date, ended_date FROM task_instance ORDER BY started_date DESC LIMIT 10;"
```

**Check business database** (pipeline results):
```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM raw.jobs;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM core.job_posting;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) FROM marts.job_skill;"
```

### Architecture Decisions

**Why Airflow Over Cron?**
- Visibility: UI shows DAG history, logs, and task status
- Retry logic: built-in retry configuration (e.g., 1 retry with 5-min delay)
- Scalability: can extend to multiple tasks/sensors without script management
- Observability: task dependencies and execution timeline are tracked automatically

**Why Daily Schedule at 03:00 UTC?**
- Off-peak to avoid contention with peak business hours
- Allows 24-hour window for incremental reloads (idempotency via file MD5)
- Provides fresh data by morning business hours

**Why No External Sensors?**
- File is uploaded manually or via batch process (no need to wait for arrivals)
- Current scope does not include SLA monitoring or dynamic triggering
- Can be added in future phases if source data arrives on a known schedule

### Next Steps

- Monitor dbt test coverage and add custom data quality checks as needed
- Consider materializing aggregated marts (e.g., skill frequency, salary trends)
- Implement incremental materialization if processing large data volumes regularly
- Extend Airflow with alerting (email/Slack on task failure)
- Implement data quality checks as separate dbt tests for anomaly detection
