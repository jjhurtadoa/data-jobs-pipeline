/*
Core dimension: Skill.

One row per unique skill, sourced from both job_skills and job_type_skills arrays.
This is the canonical dictionary of all skills in the dataset.
*/

with all_skills as (
  select distinct skill_name from {{ ref('stg_job_skills_exploded') }}
  union all
  select distinct skill_name from {{ ref('stg_job_type_skills_exploded') }}
)

select
  md5(skill_name) as skill_id,
  skill_name,
  current_timestamp() as created_at
from all_skills
where skill_name is not null and skill_name != ''
order by skill_name
