/*
Staging model: explode job_skills array into individual skill rows.

This model takes the deduplicated and aggregated job_skills array from stg_raw_jobs
and creates one row per skill, ready for dimension building and the job_skill bridge table.

No skill_category here: job_skills is a flat list with no grouping.
Category-aware skills come from stg_job_type_skills_exploded.
*/

with raw_skills as (
  select
    raw_job_id,
    business_key,
    job_skills_array,
    ingested_at
  from {{ ref('stg_raw_jobs') }}
  where job_skills_array is not null and array_length(job_skills_array, 1) > 0
),

exploded as (
  select
    raw_job_id,
    business_key,
    lower(trim(skill_value)) as skill_name,
    ingested_at
  from raw_skills,
  lateral unnest(job_skills_array) as skill_value
)

select
  md5(concat(cast(raw_job_id as varchar), '||', skill_name)) as skill_assignment_id,
  raw_job_id,
  business_key,
  skill_name,
  ingested_at
from exploded
where skill_name is not null and skill_name != ''
