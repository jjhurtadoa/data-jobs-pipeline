/*
Core dimension: Job Title Category.

One row per unique job_title_short value.
*/

with base as (
  select nullif(lower(trim(job_title_short)), '') as job_title_short
  from {{ ref('stg_raw_jobs') }}
)

select
  md5(job_title_short) as title_cat_id,
  job_title_short,
  current_timestamp as created_at
from base
where job_title_short is not null
group by job_title_short
