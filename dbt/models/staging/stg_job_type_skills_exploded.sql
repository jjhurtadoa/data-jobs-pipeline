/*
Staging model: explode job_type_skills dictionary into individual skill rows with categories.

This model parses the job_type_skills JSONB dictionary (e.g., {"programming": ["python", "sql"]})
and creates one row per skill, preserving the category grouping from the original data.
*/

with raw_grouped_skills as (
  select
    raw_job_id,
    business_key,
    job_type_skills,
    ingested_at
  from {{ ref('stg_raw_jobs') }}
  where job_type_skills is not null
),

-- Expand category -> skills entries from JSONB
parsed as (
  select
    rgs.raw_job_id,
    rgs.business_key,
    lower(trim(entry.skill_category)) as skill_category,
    entry.skills_json,
    rgs.ingested_at
  from raw_grouped_skills rgs
  cross join lateral jsonb_each(rgs.job_type_skills) as entry(skill_category, skills_json)
  where trim(entry.skill_category) != ''
),

-- Explode skill arrays and normalize each skill value
exploded as (
  select
    p.raw_job_id,
    p.business_key,
    p.skill_category,
    lower(trim(skill_item.skill_name)) as skill_name,
    p.ingested_at
  from parsed p
  cross join lateral jsonb_array_elements_text(
    case
      when jsonb_typeof(p.skills_json) = 'array' then p.skills_json
      when p.skills_json is null then '[]'::jsonb
      else jsonb_build_array(p.skills_json)
    end
  ) as skill_item(skill_name)
  where trim(skill_item.skill_name) != ''
)

select
  md5(concat(cast(raw_job_id as varchar), '||', skill_category, '||', skill_name)) as grouped_skill_assignment_id,
  raw_job_id,
  business_key,
  skill_name,
  skill_category,
  ingested_at
from exploded
where skill_name is not null and skill_name != ''
