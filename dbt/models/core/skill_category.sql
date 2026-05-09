/*
Core dimension: Skill Category.

One row per unique skill category, sourced from job_type_skills groupings.
These are the domain categories like 'programming', 'cloud', 'databases', etc.
*/

select
  md5(skill_category) as skill_cat_id,
  skill_category as category_name,
  current_timestamp() as created_at
from {{ ref('stg_job_type_skills_exploded') }}
where skill_category is not null
group by skill_category
