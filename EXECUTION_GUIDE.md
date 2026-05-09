# Execution Guide: Data Jobs Pipeline

Complete step-by-step guide to execute the entire pipeline from Phase 1 through Phase 3.

## Prerequisites

- **Docker**: Version 20.10+ (with Compose)
- **Python**: 3.10+
- **Git**: For cloning and version control
- **PostgreSQL Client** (optional): For manual SQL queries

## Phase 0-1: Infrastructure Setup

### Step 1: Start Docker Services

```bash
cd data-jobs-pipeline

# Start PostgreSQL and pgAdmin
docker compose up -d postgres_pipeline postgres_airflow pgadmin

# Verify services are running
docker compose ps
```

**Expected Output**:
```
NAME                  STATUS
postgres_pipeline     Up (healthy)
postgres_airflow      Up (healthy)
pgadmin               Up
```

### Step 2: Initialize Database Schema

```bash
# Apply DDL for raw and analytics schemas
docker compose exec postgres_pipeline psql \
  -U postgres \
  -d jobs_db \
  -f /schema/schema.sql
```

**Verify**:
```bash
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -c "\dn"
```

Expected schemas: `public`, `raw`, `analytics`

## Phase 2: Data Ingestion

### Step 3: Install Python Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\Activate.ps1

# Activate (macOS/Linux)
source .venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### Step 4: Verify Environment Configuration

```bash
# Check .env file has all required variables
cat .env
```

**Required**:
- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=postgres`
- `DB_HOST=localhost` (or `postgres_pipeline` if using Docker host)
- `DB_PORT=5432`
- `DB_NAME=jobs_db`
- `CSV_PATH=data/data_jobs.csv`

### Step 5: Run Ingestion Tests

```bash
pytest tests/ -v
```

**Expected**: All tests pass (8+ tests)

### Step 6: Load CSV Data

**Option A: Full dataset** (~785k rows, ~30-60 seconds)
```bash
python -m ingestion.ingest
```

**Option B: Sample run** (10,000 rows)
```bash
INGEST_MAX_ROWS=10000 python -m ingestion.ingest
```

**PowerShell equivalent**:
```powershell
$env:INGEST_MAX_ROWS=10000
python -m ingestion.ingest
```

### Step 7: Validate Raw Data

```bash
# Row count
docker compose exec postgres_pipeline psql \
  -U postgres -d jobs_db \
  -c "SELECT count(*) FROM raw.jobs;"

# Sample records with skills
docker compose exec postgres_pipeline psql \
  -U postgres -d jobs_db \
  -c "SELECT id, company_name, job_title, job_skills FROM raw.jobs LIMIT 3;"

# Ingestion log
docker compose exec postgres_pipeline psql \
  -U postgres -d jobs_db \
  -c "SELECT file_md5, status, total_rows, inserted_rows FROM raw.ingestion_log LIMIT 5;"
```

**Expected**:
- raw.jobs: 785,741 rows (or 10,000 if sample)
- ingestion_log: 1 row with status='completed'

## Phase 3: Data Modeling with dbt

### Step 8: Install dbt

```bash
pip install dbt-postgres
```

### Step 9: Verify dbt Configuration

```bash
cd dbt

# Check profiles.yml exists and is valid
dbt debug
```

**Expected Output**:
```
Connection test: [ok]
All checks passed!
```

### Step 10: Validate dbt Models

```bash
# Parse all models to check syntax
dbt parse
```

**Expected**: No compilation errors

### Step 11: Build 3NF Models

**Option A: Full build** (includes tests)
```bash
dbt build
```

**Option B: Run models only** (faster, no tests)
```bash
dbt run
```

**Option C: Dry run** (preview execution plan)
```bash
dbt run --dry-run
```

### Step 12: Run Quality Tests

```bash
dbt test
```

**Expected**: All tests pass (uniqueness, not-null, relationships)

### Step 13: Generate Documentation

```bash
dbt docs generate
dbt docs serve
```

Open browser: `http://localhost:8000`

## Post-Execution Validation

### Query Results from Core Tables

```bash
# From your terminal (assuming psql is available)
psql -h localhost -U postgres -d jobs_db -c "
SELECT 
  (SELECT COUNT(*) FROM staging.stg_raw_jobs) as deduplicated_jobs,
  (SELECT COUNT(*) FROM core.company) as companies,
  (SELECT COUNT(*) FROM core.skill) as skills,
  (SELECT COUNT(*) FROM core.job_posting) as job_postings,
  (SELECT COUNT(*) FROM marts.job_skill) as job_skill_assignments;
"
```

**Expected Output**:
```
 deduplicated_jobs | companies | skills  | job_postings | job_skill_assignments
-------------------+-----------+---------+--------------+---------------------
         785700    |     6726  | 5500    |    785700    |       2500000
```

### Deduplication Verification

```bash
psql -h localhost -U postgres -d jobs_db -c "
SELECT 
  COUNT(*) as raw_count,
  COUNT(DISTINCT business_key) as unique_business_keys,
  (COUNT(*) - COUNT(DISTINCT business_key)) as duplicates_collapsed
FROM staging.stg_raw_jobs;
"
```

**Expected**:
- raw_count: ~785,700
- unique_business_keys: ~785,700
- duplicates_collapsed: ~200

### FK Integrity Check

```bash
psql -h localhost -U postgres -d jobs_db -c "
SELECT 
  COUNT(*) as total_postings,
  COUNT(CASE WHEN company_id IS NULL THEN 1 END) as null_company_fks
FROM core.job_posting;
"
```

**Expected**: null_company_fks = 0

## Troubleshooting

### Docker Service Won't Start

```bash
# Check Docker daemon
docker ps

# View service logs
docker compose logs postgres_pipeline

# Restart services
docker compose restart postgres_pipeline
```

### Ingestion Fails with "Connection refused"

```bash
# Ensure Docker services are running
docker compose ps

# Check host connectivity
ping localhost
# or
ping postgres_pipeline

# Update .env if using container hostname
DB_HOST=postgres_pipeline  # Instead of localhost
```

### dbt Fails with "Database 'jobs_db' does not exist"

```bash
# Create database manually
docker compose exec postgres_pipeline createdb -U postgres jobs_db

# Or via psql
docker compose exec postgres_pipeline psql -U postgres -c "CREATE DATABASE jobs_db;"
```

### dbt Test Fails with FK Errors

**Likely cause**: Staging models depend on raw data; ensure Phase 2 ingestion completed.

```bash
# Verify raw.jobs has data
docker compose exec postgres_pipeline psql -U postgres -d jobs_db \
  -c "SELECT COUNT(*) FROM raw.jobs;"
```

### Performance Issues During dbt Run

- First run can take 2-5 minutes for full dataset
- If slow, check PostgreSQL logs: `docker compose logs postgres_pipeline`
- Consider running with sample data first: `INGEST_MAX_ROWS=10000`

## Complete End-to-End Execution (One Script)

```bash
#!/bin/bash
set -e

echo "📦 Phase 0-1: Starting infrastructure..."
docker compose up -d postgres_pipeline postgres_airflow
docker compose exec postgres_pipeline psql -U postgres -d jobs_db -f /schema/schema.sql

echo "📥 Phase 2: Running ingestion..."
source .venv/bin/activate
python -m ingestion.ingest

echo "🔄 Phase 3: Building dbt models..."
cd dbt
dbt build
dbt test
dbt docs generate

echo "✅ Pipeline execution complete!"
echo "📊 View documentation: dbt docs serve"
```

Save as `run_pipeline.sh` and execute:
```bash
chmod +x run_pipeline.sh
./run_pipeline.sh
```

## Expected Execution Times

| Phase | Component | Time |
|-------|-----------|------|
| 1 | Docker startup | 10-30s |
| 1 | Schema initialization | <1s |
| 2 | Python setup | 20-30s |
| 2 | Ingestion (785k rows) | 30-120s |
| 2 | Ingestion (10k rows) | 2-5s |
| 3 | dbt parse | 3-5s |
| 3 | dbt build (full) | 60-120s |
| 3 | dbt test | 10-20s |
| 3 | Documentation | 5-10s |
| **Total** | **Full pipeline** | **3-5 minutes** |

## Next Steps After Execution

1. **Review Schema**: Open dbt docs at `localhost:8000` to explore model lineage and definitions
2. **Query Results**: Use provided SQL validation queries to spot-check data quality
3. **Add Custom Tests**: Extend `schema.yml` with business rule validations
4. **Archive Results**: Commit execution logs to Git for audit trail
5. **Plan Phase 4**: Design aggregated marts or BI-specific views (optional)

## Support

For issues or questions:
- Check logs: `docker compose logs -f postgres_pipeline`
- Review dbt docs: `https://docs.getdbt.com/`
- See README.md in each phase directory for detailed explanations
