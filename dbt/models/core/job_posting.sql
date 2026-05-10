/*
Core table: Job Posting (main 3NF entity).

This is the central entity representing each unique job posting.
All dimensional FKs point to their respective lookup tables.
Salary fields remain here as optional attributes from source data.
*/

select
  md5(s.business_key)               as job_id,
  s.business_key,
  s.raw_job_id,
  s.job_title_short,
  s.job_title                        as job_title_full,
  s.job_location,
  s.search_location,
  s.job_posted_date                  as posted_date,
  s.job_work_from_home               as work_from_home,
  s.job_no_degree_mention            as no_degree_mention,
  s.job_health_insurance             as health_insurance,
  s.salary_year_avg,
  s.salary_hour_avg,
  md5(nullif(lower(trim(s.company_name)), '')) as company_id,
  md5(nullif(lower(trim(s.job_title_short)), '')) as title_cat_id,
  md5(nullif(lower(trim(s.job_schedule_type)), '')) as schedule_type_id,
  md5(nullif(lower(trim(s.job_via)), '')) as platform_id,
  md5(nullif(lower(trim(s.job_country)), '')) as country_id,
  md5(nullif(lower(trim(s.salary_rate)), '')) as rate_type_id,
  s.ingested_at,
  current_timestamp                  as created_at
from {{ ref('stg_raw_jobs') }} s
where nullif(trim(s.company_name), '') is not null
