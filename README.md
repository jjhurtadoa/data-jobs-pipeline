# Data Jobs Pipeline

An end-to-end data pipeline that ingests raw job posting data from CSV and transforms it into a well-structured, normalized relational model (3NF) — production-ready, containerized, and fully orchestrated.

## Tech Stack

| Layer | Tool |
|-------|------|
| Ingestion | Python 3.11 |
| Storage | PostgreSQL 16 |
| Transformation | dbt-postgres |
| Orchestration | Apache Airflow 2.10 |
| Infrastructure | Docker Compose |
| CI/CD | GitHub Actions |
| Testing & Lint | pytest · ruff |

## Quick Start

**Prerequisites:** Docker Desktop running, Git.

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd data-jobs-pipeline

# 2. Set up environment variables
cp .env.example .env

# 3. Bring up the full stack (databases + Airflow)
docker compose up -d

# 4. Wait ~30s for Airflow to initialize, then trigger the pipeline
docker compose exec airflow-webserver airflow dags test data_jobs_pipeline 2026-05-10

# 5. Verify results
docker compose exec postgres_pipeline psql -U postgres -d jobs_db \
  -c "SELECT COUNT(*) FROM core.job_posting;"
```

| Service | URL | Credentials |
|---------|-----|-------------|
| Airflow UI | http://localhost:8080 | admin / admin |
| pgAdmin | http://localhost:5050 | admin@admin.com / admin |

---

## Architecture

### Data Flow

```
data_jobs.csv
      │
      │  Python (ingestion/)
      ▼
 raw.jobs  ←  raw.ingestion_log
      │
      │  dbt staging
      ▼
 stg_raw_jobs          ← dedup + normalize
 stg_job_skills_exploded
 stg_job_type_skills_exploded
      │
      │  dbt core
      ▼
 job_posting  ←─── company · country · platform
                    schedule_type · salary_rate_type
                    job_title_category
      │
      │  dbt marts
      ▼
 job_skill  (M:N bridge: job_posting ↔ skill · skill_category)
```

### Ingestion

Reads `data/data_jobs.csv` and loads it into `raw.jobs` (PostgreSQL). Implemented in `ingestion/`.

**Target schema and DDL bootstrap**

Ingestion always targets the `raw` schema in PostgreSQL (`raw.jobs` as landing table and `raw.ingestion_log` for execution metadata).

The DDL source of truth is `schema/schema.sql`. Before ingestion, the pipeline starts PostgreSQL and applies this script to ensure required schemas/tables exist.

```bash
# 1) Start PostgreSQL service
docker compose up -d postgres_pipeline

# 2) Create/update schemas and raw tables
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -f schema/schema.sql

# 3) Optional sanity check
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "\dt raw.*"
```

**Idempotency via MD5 fingerprint**

Before any insert, an MD5 hash of the entire CSV file is computed. If a completed entry for that hash already exists in `raw.ingestion_log`, the run is skipped entirely — re-running ingestion on an already-loaded file is always safe.

**Semi-structured columns**

Two columns arrive as Python-literal strings embedded in the CSV:

| Column | Source format | Parsed as |
|--------|--------------|-----------|
| `job_skills` | `"['python', 'sql', 'spark']"` | `list[str]` → stored as JSONB |
| `job_type_skills` | `"{'core': ['python'], 'cloud': ['aws']}"` | `dict[str, list[str]]` → stored as JSONB |

Parsing uses `ast.literal_eval` with strict validation. Each row is profiled independently:
- **missing**: field is null/empty → stored as `NULL`, no warning raised
- **invalid**: field has content but fails parsing → `NULL` stored, warning counted

**Normalization applied to every row**

- Text fields: `strip()`, empty strings → `NULL`
- Booleans: accepts `True/False`, `1/0`, `yes/no`, `t/f`
- Decimals: `salary_year_avg`, `salary_hour_avg` parsed to `Decimal` (avoids float precision loss)
- `job_posted_date`: kept as `TEXT` in raw — type casting deferred to dbt staging

**Logging**

Each run emits a structured summary log line and registers a row in `raw.ingestion_log`:

```
skipped | file_md5 | total_rows | inserted_rows | parse_warnings
job_skills_missing | job_skills_invalid | job_type_skills_missing | job_type_skills_invalid
```

**Run ingestion (after schema bootstrap)**

```bash
# Full run
python -m ingestion.ingest

# Smoke run (limited rows for testing)
INGEST_MAX_ROWS=500 python -m ingestion.ingest   # Linux/Mac
$env:INGEST_MAX_ROWS=500; python -m ingestion.ingest  # PowerShell
```

**Verify loaded data**

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db \
  -c "SELECT file_md5, status, total_rows, inserted_rows, parse_warnings, finished_at FROM raw.ingestion_log ORDER BY finished_at DESC LIMIT 5;"
```

**Unit tests** (`tests/test_parsers.py`, `tests/test_ingest.py`)

```bash
pytest tests/test_parsers.py tests/test_ingest.py -v
```

Key test coverage:

| Test | What it validates |
|------|------------------|
| `test_parse_job_skills_valid_list` | Parses `"['python','sql']"` → `["python", "sql"]` |
| `test_parse_job_type_skills_ignores_empty_values` | Drops blank keys and empty lists |
| `test_build_job_record_counts_parse_warnings` | Malformed fields increment warning counter |
| `test_build_job_record_profiles_missing_semistructured_values` | Null fields count as missing, not invalid |
| `test_compute_file_md5_is_deterministic` | Same file always produces same hash |
| `test_parse_bool_variants` | Handles `True`, `0`, `unknown` |
| `test_parse_decimal_variants` | Handles valid/empty/bad decimal strings |


### Relational Modeling (3NF)

After ingestion into `raw.jobs`, dbt transforms the data into a normalized 3NF model in PostgreSQL.

Entity relationships are documented in the ER diagram: [Entity-Relationship Diagram](Entity-Relationship%20Diagram.svg).

**Layered dbt architecture**

- `staging`: parse, normalize, and explode semi-structured fields
- `core`: 3NF entities with PK/FK constraints
- `marts`: bridge table that materializes the many-to-many relationship (`marts.job_skill`)

Main models:
- `staging.stg_raw_jobs`: deduplicated base records
- `staging.stg_job_skills_exploded`: array skills exploded to one row per skill
- `staging.stg_job_type_skills_exploded`: dict skills exploded to category + skill rows
- `core.job_posting`: central fact-like 3NF entity with foreign keys
- `core.company`, `core.country`, `core.platform`, `core.schedule_type`, `core.salary_rate_type`, `core.job_title_category`, `core.skill`, `core.skill_category`: normalized dimensions
- `marts.job_skill`: many-to-many bridge between posting and skills

**Deduplication logic**

`stg_raw_jobs` applies a business-key deduplication strategy. When two or more records are identical in all attributes except `job_skills` and `job_type_skills`, staging keeps a single canonical posting and merges both skill sources without duplicates.

In practice:
- one posting row is preserved in `stg_raw_jobs`
- `job_skills` is merged as a distinct set
- `job_type_skills` is merged by category with distinct skill values

This avoids duplicate postings while retaining complete skill coverage.

**Why this is 3NF**

- Multivalued attributes (`job_skills`, `job_type_skills`) are extracted into separate entities and a bridge table
- Reference domains (company, country, platform, etc.) are normalized into lookup tables
- `core.job_posting` stores only attributes that depend on `job_id` and references dimensions through foreign keys

**Data quality tests in dbt**

Native dbt tests used in `schema.yml`:
- `not_null`: mandatory keys and required columns
- `unique`: entity keys and uniqueness constraints
- `relationships`: foreign key integrity between child and parent tables

Custom tests developed for this project:
- Generic tests in `dbt/tests/generic/`:
     - `composite_key_unique.sql`
     - `dates_not_future.sql`
- Specific tests in `dbt/tests/specific/`:
     - `job_posting_matches_staging.sql`
     - `job_skill_unique_combination.sql`

Together, these checks make the 3NF layer behave with transactional-grade consistency (PK/FK integrity, uniqueness, and business-rule validation).

**Run dbt transformation and tests**

```bash
# From repository root
cd dbt

# Validate connection/profile
dbt debug

# Build staging + core + marts
dbt build

# Run tests only (optional extra run)
dbt test
```

**Validate model outputs in PostgreSQL**

```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) AS job_postings FROM core.job_posting;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT COUNT(*) AS bridge_rows FROM marts.job_skill;"
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "SELECT job_id, skill_id, skill_cat_id, COUNT(*) AS cnt FROM marts.job_skill GROUP BY 1,2,3 HAVING COUNT(*) > 1;"
```

Expected checks:
- `core.job_posting` with non-zero row count
- `marts.job_skill` with non-zero row count
- duplicate query returns 0 rows



### Orchestration

Airflow orchestrates the pipeline defined in `airflow/dags/pipeline_dag.py` with DAG id `data_jobs_pipeline`.

**Execution graph**

```text
ingest_raw_jobs
     -> dbt_run_models
     -> dbt_run_tests
```

**DAG configuration**

- Schedule: daily at `03:00 UTC` (`0 3 * * *`)
- `catchup=False` to avoid retroactive backfills
- `max_active_runs=1` to prevent overlapping runs
- Retries: `1` with `5` minutes delay

**Task commands (as implemented)**

- `ingest_raw_jobs`: `cd /opt/airflow/project && python -m ingestion.ingest`
- `dbt_run_models`: `cd /opt/airflow/project/dbt && python -m dbt.cli.main run --fail-fast`
- `dbt_run_tests`: `cd /opt/airflow/project/dbt && python -m dbt.cli.main test --fail-fast`

dbt tasks inject `DBT_PROFILES_DIR=/opt/airflow/project/dbt`, and all tasks use `append_env=True` so container environment variables (database/dbt settings from Docker Compose) are preserved.

**Run orchestration locally**

```bash
# 1) Initialize Airflow metadata DB and user
docker compose up -d airflow-init

# 2) Start scheduler + webserver
docker compose up -d airflow-scheduler airflow-webserver

# 3) Validate services
docker compose ps

# 4) Execute one full DAG run (without waiting for schedule)
docker compose exec airflow-webserver airflow dags test data_jobs_pipeline <YYYY-MM-DD>
```

Optional observability:

```bash
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-webserver
```

**How to test orchestration**

Unit tests (DAG structure) in `tests/test_dag.py` validate:
- DAG imports with no errors
- expected task ids and task count
- linear dependencies (`ingest_raw_jobs -> dbt_run_models -> dbt_run_tests`)
- BashOperator usage
- `--fail-fast` in dbt tests
- `DBT_PROFILES_DIR` injection in dbt tasks

Run DAG unit tests:

```bash
pytest tests/test_dag.py -v
```

If running on Windows host, execute inside Airflow container:

```bash
docker compose exec airflow-webserver bash -c "cd /opt/airflow/project && pytest tests/test_dag.py -v"
```

Integration test (real task execution):

```bash
docker compose exec airflow-webserver airflow dags test data_jobs_pipeline <YYYY-MM-DD>
```

Success criteria:
- all 3 tasks finish in `success`
- `dbt_run_tests` finishes without failing assertions
- row counts are available in `raw.jobs`, `core.job_posting`, and `marts.job_skill`

### CI/CD

The repository uses two GitHub Actions workflows:

- `CI Pipeline` (`.github/workflows/ci.yml`)
- `CD - Generate Artifacts` (`.github/workflows/cd.yml`)

**When each workflow runs**

CI (`ci.yml`):
- runs on `push` to `main` and `develop`
- runs on `pull_request` targeting `main` and `develop`

CD (`cd.yml`):
- runs only on `push` to `main`
- does not run on pull requests

In short:
- PRs get full validation (CI)
- merges/direct pushes to `main` get validation (CI) plus artifact generation (CD)

**CI workflow: what it validates**

Jobs run in parallel:
- `lint`: runs `ruff check . --extend-exclude .venv,dbt_project`
- `unit-tests`: runs `pytest tests/test_parsers.py tests/test_ingest.py -v`
- `dbt-tests`: starts PostgreSQL service, initializes `schema/schema.sql`, ingests sample data with `python -m ingestion.ingest`, then runs `dbt build --fail-fast`
- `airflow-dag-tests`: installs Airflow and runs `pytest tests/test_dag.py -v`

Final gate:
- `summary` depends on all previous jobs and fails the pipeline if any required job failed

**CD workflow: what it publishes**

On `push` to `main`, CD:
- starts PostgreSQL service in GitHub Actions
- initializes schema via `schema/schema.sql`
- ingests data (`python -m ingestion.ingest`)
- runs `dbt build --fail-fast`
- generates docs with `dbt docs generate`
- uploads `dbt/target/` as artifact `dbt-docs` (30 days retention)

This CD pipeline is artifact-oriented (documentation output), not application deployment.

**Environment strategy in CI/CD**

- dbt profile is parameterized through environment variables (`DBT_POSTGRES_*`)
- `DBT_PROFILES_DIR` points to the repository dbt folder in runners
- ingestion job receives runtime database variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `CSV_PATH`)

This keeps the same code working across local Docker, Airflow containers, and GitHub runners without hardcoded credentials.

### Next Step: Conceptual Design of an Analytical Model (OLAP)

The next layer is a dimensional model built on top of the current 3NF system of record. The key starting point is the model already implemented in this project: it is very close to a star structure because `job_posting` is the central entity, the reference domains are already normalized, and the skill relationship already exists as a bridge. The OLAP design should reuse that foundation instead of redrawing it from zero.

**Recommended approach: Star Schema**

I would build a star schema in a dedicated analytics layer, keeping the 3NF model as the governed source and projecting it into BI-friendly dimensions and facts.

**Fact table**

Main fact table:
- `fact_job_posting`

Grain:
- one row per job posting after deduplication and normalization
- if historical tracking is required, the grain can be extended to one row per `job_posting_id` per `ingestion_date` or snapshot date

This grain supports counting postings, analyzing salary, and slicing by company, country, platform, schedule type, and date.

**Main dimensions**

Core dimensions:
- `dim_company`
- `dim_country`
- `dim_platform`
- `dim_schedule_type`
- `dim_salary_rate_type`
- `dim_job_title_category`
- `dim_date`

Additional analytical dimensions:
- `dim_skill`
- `dim_skill_category`

**Measures in the fact table**

Key numerical metrics:
- `job_count` = 1 per fact row, used for counting postings
- `salary_year_avg`
- `salary_hour_avg`
- `salary_min`
- `salary_max`
- `posted_jobs` or `active_job_count` if the business logic distinguishes active records
- `skill_count` or `distinct_skill_count` if computed at the fact layer or in a companion mart

These measures allow dashboards to show volume, pay distribution, and skill intensity by segment.

**Design challenge 1: `job_skills` as a many-to-many relationship**

`job_skills` does not fit directly into a single fact row because a job can have many skills and a skill can belong to many jobs. In the current 3NF model this is already solved with the existing bridge table (`marts.job_skill`), so the OLAP layer should reuse that relationship.

In the dimensional layer, that same bridge can be exposed as the many-to-many link between `fact_job_posting` and `dim_skill`.

Why a bridge table:
- preserves the many-to-many structure without flattening or duplicating the fact table
- allows skill-based slicing and counting in BI tools
- avoids double counting when a job has multiple skills
- reuses the normalized relationship already present in the 3NF model

If needed, the bridge can include weighting logic so one job contributes fairly across its skills.

**Design challenge 2: multiple boolean flags**

Boolean columns should not be scattered across the fact table if they are used as low-cardinality descriptive attributes. I would group them into a mini-dimension / junk dimension.

Suggested dimension:
- `dim_job_flags`

With three binary flags, this dimension has exactly $2^3 = 8$ possible rows, one for each combination of values. The fact table stores only a small integer key instead of three separate boolean columns.

Example structure:

```text
dim_job_flags (
     job_flags_key PK,
     work_from_home,
     no_degree_mention,
     health_insurance,
     remote_label,
     degree_label,
     benefits_label
)
```

Why this works:
- reduces the width of the fact table
- allows filtering by any combination of flags with a simple join
- avoids complex WHERE clauses over multiple boolean columns
- fits naturally with low-cardinality attributes already present in the source model

In the fact table, only `job_flags_key` would be stored.

**Conceptual star layout**

```text
                     dim_date
                           |
dim_company ---- fact_job_posting ---- dim_country
       |              |   |   |            |
       |              |   |   |            |
       |         dim_platform  |      dim_job_flags
       |              |        |
       |         dim_schedule  |
       |              |        |
       |      dim_salary_rate   |
       |                       |
       +---- bridge_job_skill --+---- dim_skill
                                        |
                                dim_skill_category

                     dim_job_title_category
```

The important idea is that `fact_job_posting` is the center, `dim_date` is a direct dimension of the fact, `job_skills` remain on the bridge, and the boolean flags are compressed into `dim_job_flags`.

**Why this design works for BI**

- `fact_job_posting` supports high-level volume and salary analysis
- dimensions provide consistent slicing by company, geography, platform, schedule, title, date, and flags
- the existing skill bridge preserves many-to-many analysis without duplication
- the junk dimension keeps boolean flags manageable and query-friendly

**Example dashboard questions this model answers**

- how many jobs were posted per month by company?
- which skills are most common for each job title category?
- what is the average salary by country and platform?
- how do remote and on-site roles differ in volume and compensation?

**Recommended implementation sequence**

1. Keep the current 3NF model as the source of truth.
2. Reuse the existing `job_posting`-centered model as the conceptual base for the star schema.
3. Materialize conformed dimensions in a dedicated analytics schema.
4. Expose `fact_job_posting` at the posting grain.
5. Reuse the existing skill bridge as the analytic link for many-to-many skill analysis.
6. Add `dim_job_flags` as a junk dimension only if the dashboard needs to group boolean attributes.
7. Expose BI-ready marts or views for the dashboard layer.


