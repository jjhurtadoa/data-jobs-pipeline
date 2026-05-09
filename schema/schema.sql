-- Raw schema (landing zone for CSV data)
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.jobs (
	id                    SERIAL PRIMARY KEY,
	job_title_short       TEXT,
	job_title             TEXT,
	job_location          TEXT,
	job_via               TEXT,
	job_schedule_type     TEXT,
	job_work_from_home    BOOLEAN,
	search_location       TEXT,
	job_posted_date       TEXT,
	job_no_degree_mention BOOLEAN,
	job_health_insurance  BOOLEAN,
	job_country           TEXT,
	salary_rate           TEXT,
	salary_year_avg       NUMERIC(12,2),
	salary_hour_avg       NUMERIC(8,2),
	company_name          TEXT,
	job_skills            JSONB,
	job_type_skills       JSONB,
	ingested_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Analytics schema (destination for 3NF dbt models)
CREATE SCHEMA IF NOT EXISTS analytics;
