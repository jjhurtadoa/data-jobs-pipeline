/*
Staging model: explode job_type_skills dictionary into individual skill rows with categories.

This model parses the job_type_skills serialized dictionary (e.g., {'programming': ['python', 'sql']})
and creates one row per skill, preserving the category grouping from the original data.
*/

with raw_grouped_skills as (
  select
    raw_job_id,
    business_key,
    job_type_skills,
    ingested_at
  from {{ ref('stg_raw_jobs') }}
  where job_type_skills is not null and job_type_skills != ''
),

-- Parse dictionary and extract category:skills pairs
parsed as (
  select
    raw_job_id,
    business_key,
    ingested_at,
    (regexp_matches(job_type_skills, '''([^']*)'': \[([^\]]*)\]', 'g'))[1] as skill_category,
    (regexp_matches(job_type_skills, '''([^']*)'': \[([^\]]*)\]', 'g'))[2] as skills_list
  from raw_grouped_skills
),

-- Extract individual skills from the list
exploded as (
  select
    raw_job_id,
    business_key,
    skill_category,
    trim(regexp_split_to_table(skills_list, ',')) as skill_name_quoted,
    ingested_at
  from parsed
  where skills_list is not null
)

select
  md5(concat(cast(raw_job_id as varchar), '||', skill_category, '||', trim(both '''" from skill_name_quoted))) as grouped_skill_assignment_id,
  raw_job_id,
  business_key,
  trim(both '''" from skill_name_quoted) as skill_name,
  skill_category,
  ingested_at
from exploded
where skill_name_quoted is not null and trim(skill_name_quoted) != ''
