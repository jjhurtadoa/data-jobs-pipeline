/*
Mart table: Job Skill (M:N bridge).

Resolves the many-to-many relationship between job postings and skills.
Includes skill category information from both job_skills and job_type_skills sources.

PK: (job_id, skill_id, skill_cat_id)
*/

with job_skills_unified as (
  -- Core skills from job_skills array
  select
    md5(s.business_key) as job_id,
    md5(sk.skill_name) as skill_id,
    md5(scat.category_name) as skill_cat_id,
    s.ingested_at,
    current_timestamp() as created_at
  from {{ ref('stg_job_skills_exploded') }} s
  left join {{ ref('skill') }} sk on s.skill_name = sk.skill_name
  left join {{ ref('skill_category') }} scat on s.skill_category_hint = scat.category_name
  union all
  -- Grouped skills from job_type_skills with explicit categories
  select
    md5(s.business_key) as job_id,
    md5(sk.skill_name) as skill_id,
    md5(scat.category_name) as skill_cat_id,
    s.ingested_at,
    current_timestamp() as created_at
  from {{ ref('stg_job_type_skills_exploded') }} s
  left join {{ ref('skill') }} sk on s.skill_name = sk.skill_name
  left join {{ ref('skill_category') }} scat on s.skill_category = scat.category_name
)

-- Deduplicate: same job + skill + category should appear only once
select distinct
  job_id,
  skill_id,
  skill_cat_id,
  ingested_at,
  created_at
from job_skills_unified
where job_id is not null
  and skill_id is not null
  and skill_cat_id is not null
