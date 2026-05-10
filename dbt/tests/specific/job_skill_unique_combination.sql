select
  job_id,
  skill_id,
  skill_cat_id,
  count(*) as duplicate_count
from {{ ref('job_skill') }}
group by job_id, skill_id, skill_cat_id
having count(*) > 1
