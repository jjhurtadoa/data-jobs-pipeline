/*
Mart table: Job Skill (M:N bridge).

Resolves the many-to-many relationship between job postings and skills.
Includes skill category information from both job_skills and job_type_skills sources.

PK: (job_id, skill_id, skill_cat_id)
*/

with job_skills_unified as (
  -- Skills from flat job_skills array (no category available)
  select
    md5(s.business_key) as job_id,
    md5(sk.skill_name) as skill_id,
    null::text as skill_cat_id,
    s.ingested_at,
    current_timestamp as created_at
  from {{ ref('stg_job_skills_exploded') }} s
  left join {{ ref('skill') }} sk on s.skill_name = sk.skill_name

  union all
  -- Skills from grouped job_type_skills with explicit category
  select
    md5(s.business_key) as job_id,
    md5(sk.skill_name) as skill_id,
    md5(scat.category_name) as skill_cat_id,
    s.ingested_at,
    current_timestamp as created_at
  from {{ ref('stg_job_type_skills_exploded') }} s
  left join {{ ref('skill') }} sk on s.skill_name = sk.skill_name
  left join {{ ref('skill_category') }} scat on s.skill_category = scat.category_name
),

valid_jobs as (
  select job_id
  from {{ ref('job_posting') }}
)

-- Deduplicate: same job + skill + category should appear only once
select distinct
  js.job_id,
  js.skill_id,
  js.skill_cat_id,
  js.ingested_at,
  js.created_at
from job_skills_unified js
inner join valid_jobs v on js.job_id = v.job_id
where js.job_id is not null
  and js.skill_id is not null
