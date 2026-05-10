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

### Next Steps

- Monitor dbt test coverage and add custom data quality checks as needed
- Consider materializing aggregated marts (e.g., skill frequency, salary trends)
- Implement incremental materialization if processing large data volumes regularly
