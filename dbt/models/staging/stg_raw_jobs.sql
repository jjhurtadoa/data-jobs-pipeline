/*
Staging model: normalize and deduplicate raw job postings.

This model:
1. Casts and normalizes columns from raw.jobs
2. Computes a business key hash (excluding job_skills and job_type_skills)
3. Deduplicates by business key, preserving the first (earliest ingested) record
4. Aggregates and deduplicates skills across all duplicate records
5. Parses job_skills and job_type_skills from serialized text to arrays

The business key ensures that the same job posting (same company, title, location, date, etc.)
appearing multiple times with different skill lists is collapsed to a single row with
the union of all skills.
*/

with raw_data as (
  select
    id as raw_job_id,
    job_title_short,
    job_title,
    job_location,
    job_via,
    job_schedule_type,
    job_work_from_home,
    search_location,
    job_posted_date,
    job_no_degree_mention,
    job_health_insurance,
    job_country,
    salary_rate,
    salary_year_avg,
    salary_hour_avg,
    company_name,
    job_skills,
    job_type_skills,
    ingested_at,
    md5(
      concat_ws(
        '||',
        coalesce(company_name, ''),
        coalesce(job_title, ''),
        coalesce(job_location, ''),
        coalesce(job_posted_date, ''),
        coalesce(job_schedule_type, ''),
        coalesce(job_via, ''),
        coalesce(cast(salary_year_avg as varchar), ''),
        coalesce(cast(salary_hour_avg as varchar), ''),
        coalesce(cast(job_work_from_home as varchar), ''),
        coalesce(cast(job_no_degree_mention as varchar), ''),
        coalesce(cast(job_health_insurance as varchar), ''),
        coalesce(job_country, ''),
        coalesce(salary_rate, '')
      )
    ) as business_key
  from raw.jobs
),

ranked as (
  select
    *,
    row_number() over (
      partition by business_key
      order by ingested_at asc, raw_job_id asc
    ) as dedup_rank
  from raw_data
),

primary_records as (
  select * from ranked where dedup_rank = 1
),

-- Parse and aggregate skills from all duplicate records
aggregated_skills as (
  select
    business_key,
    -- Parse job_skills (serialized array) and collect unique skills
    array(
      select distinct elem::text
      from raw_data rd,
      lateral (
        select unnest(
          case
            when rd.job_skills is not null and rd.job_skills != ''
            then (regexp_matches(rd.job_skills, "'([^']*)'" , 'g'))[1]::text
            else null
          end
        )
      ) as elem
      where rd.business_key = aggregated_skills.business_key
      order by elem
    ) as aggregated_job_skills
  from (
    select distinct business_key from raw_data
  ) t
)

select
  pr.raw_job_id,
  pr.business_key,
  pr.job_title_short,
  pr.job_title,
  pr.job_location,
  pr.job_via,
  pr.job_schedule_type,
  pr.job_work_from_home,
  pr.search_location,
  pr.job_posted_date,
  pr.job_no_degree_mention,
  pr.job_health_insurance,
  pr.job_country,
  pr.salary_rate,
  pr.salary_year_avg,
  pr.salary_hour_avg,
  pr.company_name,
  coalesce(agg.aggregated_job_skills, array[]::text[]) as job_skills_array,
  pr.job_type_skills,
  pr.ingested_at,
  current_timestamp() as dbt_processed_at
from primary_records pr
left join aggregated_skills agg on pr.business_key = agg.business_key
