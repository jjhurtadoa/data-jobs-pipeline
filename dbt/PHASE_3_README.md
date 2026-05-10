# Phase 3: Data Modeling in 3NF with dbt

## Overview

This phase transforms raw job posting data into a **Third Normal Form (3NF)** relational model using dbt. The goal is to eliminate redundancy, resolve many-to-many relationships, and create a clean analytical foundation.

### Key Characteristics of This Model

1. **Central Entity**: `job_posting` (one row per unique job posting)
2. **Normalized Dimensions**: `company`, `country`, `platform`, `schedule_type`, `job_title_category`, `salary_rate_type`
3. **Skill Hierarchy**: `skill`, `skill_category`
4. **Many-to-Many Bridge**: `job_skill` (resolves M:N between job postings and skills)
5. **Deduplication**: Business key-based, with skill aggregation across duplicates

---

## Architecture

### Staging Layer (`staging/`)

**Purpose**: Parse, normalize, and deduplicate raw data.

- **`stg_raw_jobs`**
  - Computes deterministic business key (MD5) excluding skills
  - Deduplicates by business key, keeping earliest record
  - Aggregates and deduplicates skills across all duplicate records
  - Converts serialized skill lists/dicts to arrays
  
- **`stg_job_skills_exploded`**
  - Explodes `job_skills` array into individual rows
  - One row per skill per job
  
- **`stg_job_type_skills_exploded`**
  - Parses `job_type_skills` dictionary (grouped skills)
  - One row per skill with category
  - Preserves original grouping from source data

### Core Layer (`core/`)

**Purpose**: Create normalized 3NF tables.

**Dimensions** (Lookup Tables):
- `company`: Unique companies (~6,726 values)
- `country`: Unique countries (~121 values)
- `platform`: Job posting channels (~702 values, e.g., LinkedIn)
- `schedule_type`: Employment types (~18 values, e.g., Full-time)
- `job_title_category`: Job title categories (~10 values)
- `salary_rate_type`: Salary periods (~3 values: year, hour, month)
- `skill`: Unique skills (canonicalized from both skill arrays)
- `skill_category`: Skill groupings (from `job_type_skills` keys)

**Fact Table**:
- `job_posting`: Central entity with all dimensional FKs
  - Salary fields remain inline (sparse, ~95% null)
  - No dependent attributes on non-key columns

### Marts Layer (`marts/`)

**Purpose**: Serve analytical queries.

- **`job_skill`** (Bridge Table)
  - Resolves M:N between `job_posting` and `skill`
  - PK: `(job_id, skill_id, skill_cat_id)`
  - Deduplicates skill assignments across sources

---

## Deduplication Strategy

**Problem**: ~200 duplicate job postings with identical content except for skills.

**Solution** (in `stg_raw_jobs`):

1. **Business Key** (excludes skills):
   ```
   MD5(company_name || job_title || job_location || job_posted_date || 
       job_schedule_type || job_via || salary_year_avg || salary_hour_avg ||
       job_work_from_home || job_no_degree_mention || job_health_insurance ||
       job_country || salary_rate)
   ```

2. **For each business key**:
   - Keep the **first (earliest ingested)** record as primary
   - Aggregate all **unique skills** from all duplicates
   - Merge `job_skills` arrays and `job_type_skills` dictionaries
   - Result: one posting with unified skill set

3. **Result**: 785,741 → ~785,700 unique postings (200 collapsed)

---

## 3NF Compliance

### Why This Design Is 3NF

| Entity | Rationale |
|--------|-----------|
| `company` | Eliminates transitive dependency: posting → company_name → company metadata (future-proof) |
| `country` | Normalizes geographic dimension (~121 values repeat 10K+ times) |
| `platform` | Resolves dependency: posting → job_via → platform metadata |
| `schedule_type` | Controlled vocabulary (18 values); 3NF requires separate table |
| `job_title_category` | 10 unique values, high redundancy; lookup ensures consistency |
| `salary_rate_type` | Closed domain (year/hour/month); belongs in catalog |
| `job_skill` | Resolves 1NF violation (multivalued `job_skills` attribute) |
| `job_posting` | Central entity; all non-key attributes depend only on `job_id` |

### Why Fields Remain Inline in `job_posting`

- **`job_location`, `search_location`**: Free-form text (1,935+ unique values); no business key
- **Salary fields**: Sparse (95% NULL); no dependency violation
- **Boolean flags**: Direct posting attributes; no transitive dependencies

### Final Modeling Decisions Applied

1. **Mandatory company dimension for core posting grain**
  - Rows with null/blank `company_name` are excluded from `core.company` and `core.job_posting`.
  - This enforces non-null FK integrity in `job_posting.company_id`.

2. **Population alignment between central entity and bridge**
  - `marts.job_skill` only includes rows whose `job_id` exists in `core.job_posting`.
  - This prevents orphan keys in the many-to-many bridge.

3. **Staging-to-core reconciliation aligned to 3NF policy**
  - The `job_posting_matches_staging` check compares only staging rows that satisfy the company rule.
  - This avoids false negatives from intentionally excluded source rows.

4. **dbt generic test arguments updated**
  - Generic test arguments were moved under `arguments` in `schema.yml`.
  - This removes deprecation warnings and keeps project syntax future-safe.

---

## Setup & Execution

### Prerequisites

1. PostgreSQL running with `jobs_db` database
2. Raw ingestion completed (`raw.jobs` populated)
3. dbt installed: `pip install dbt-postgres`
4. dbt profile configured in `~/.dbt/profiles.yml`

### Installation

```bash
cd dbt

# Install dbt dependencies (if any)
dbt deps

# Verify connection
dbt debug
```

### Build Models

```bash
# Build all models (staging → core → marts)
dbt build

# Or specific layers
dbt build -s path:models/staging
dbt build -s path:models/core
dbt build -s path:models/marts

# Run with --select to test dependencies
dbt run --select job_posting
```

### Run Tests

```bash
# Execute all tests (relationships, uniqueness, not_null)
dbt test

# Test specific model
dbt test -s job_posting
```

### Focused Validation Checklist (After Core/Bridge Changes)

```bash
# Rebuild bridge with current core population
dbt run --select job_skill

# Verify no orphan bridge keys
dbt test --select relationships_job_skill_job_id__job_id__ref_job_posting_

# Validate selected graph used during troubleshooting
dbt build --select company job_posting job_skill
```

Expected:
- 0 failing rows in `relationships_job_skill_job_id__job_id__ref_job_posting_`
- 0 failing rows in `job_posting_matches_staging`

### Generate Docs

```bash
dbt docs generate
dbt docs serve  # Opens local server at localhost:8000
```

---

## Expected Output

After `dbt build`:

| Table | Rows | Purpose |
|-------|------|---------|
| `staging.stg_raw_jobs` | ~785,700 | Deduplicated base |
| `core.company` | ~6,726 | Lookup: companies |
| `core.country` | ~121 | Lookup: countries |
| `core.platform` | ~702 | Lookup: platforms |
| `core.schedule_type` | ~18 | Lookup: employment types |
| `core.job_title_category` | ~10 | Lookup: job titles |
| `core.salary_rate_type` | ~3 | Lookup: salary periods |
| `core.skill` | ~5,000-6,000 | Lookup: unique skills |
| `core.skill_category` | ~10 | Lookup: skill groups |
| `core.job_posting` | ~785,700 | Central: job postings with FKs |
| `marts.job_skill` | ~2-3M | Bridge: job → skills |

### Validation Queries

```sql
-- Check deduplication
SELECT COUNT(DISTINCT business_key) FROM staging.stg_raw_jobs;
-- Expected: ~785,700 (205k reductions)

-- Check FK integrity
SELECT COUNT(*) FROM core.job_posting WHERE company_id IS NULL;
-- Expected: 0 (all postings have company)

-- Check skill distribution
SELECT COUNT(*) FROM marts.job_skill;
-- Expected: 2-3M rows (multiple skills per posting)

-- Check bridge deduplication
SELECT job_id, skill_id, skill_cat_id, COUNT(*) as cnt
FROM marts.job_skill
GROUP BY job_id, skill_id, skill_cat_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows (no duplicates)
```

---

## Future: Star Schema for BI

This 3NF model is the analytical foundation. To serve BI dashboards, you would:

1. **Materialize the 3NF** as is (already optimized)
2. **Add BI-specific views** on top:
   - `mart_job_postings_denormalized` (star-like flattening)
   - `mart_skill_frequency` (aggregated skill stats)
   - `mart_company_salary_metrics` (aggregated metrics by company)
3. **Keep the 3NF pure** for operational integrity

This separation ensures that source data remains normalized while BI consumers get the denormalized views they expect.

---

## Notes

- All model names, comments, and variables are in **English**
- IDs use **MD5 hashing** (deterministic, PostgreSQL native)
- Tests include **uniqueness**, **not-null**, and **referential integrity**
- Schema documentation is in `schema.yml`
- Incremental materialization not used; all tables are full rebuilds for clarity

---

## Troubleshooting

### `dbt run` fails with "raw.jobs not found"
- Ensure Phase 1 & 2 ingestion completed
- Verify `raw` schema exists: `\dn` in psql

### FK relationships fail in tests
- Check that all dimension tables populated before `job_posting` runs
- dbt should handle this via `depends_on` references

### Skills explosion produces wrong results
- Review `stg_job_skills_exploded` output for parsing issues
- Validate source `job_skills` serialization format matches expectations

---

## Next Steps

- **Phase 4** (Optional): Aggregated marts for reporting
- **Phase 5** (Optional): Incremental processing & orchestration
- Implement quality checks (duplicate skills, business key collisions)
