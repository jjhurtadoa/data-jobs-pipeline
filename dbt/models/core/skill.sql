/*
Core dimension: Skill.

One row per unique skill, sourced from both job_skills and job_type_skills arrays.
This is the canonical dictionary of all skills in the dataset.
*/

with all_skills as (
  select skill_name from {{ ref('stg_job_skills_exploded') }}
  union
  select skill_name from {{ ref('stg_job_type_skills_exploded') }}
),

canonical_skills as (
  select nullif(lower(trim(skill_name)), '') as skill_name
  from all_skills
)

select
  md5(skill_name) as skill_id,
  skill_name,
  current_timestamp as created_at
from canonical_skills
where skill_name is not null and skill_name != ''
order by skill_name
