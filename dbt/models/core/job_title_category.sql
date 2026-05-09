/*
Core dimension: Job Title Category.

One row per unique job_title_short value.
*/

select
  md5(job_title_short) as title_cat_id,
  job_title_short,
  current_timestamp() as created_at
from {{ ref('stg_raw_jobs') }}
where job_title_short is not null
group by job_title_short
