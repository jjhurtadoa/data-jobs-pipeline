/*
Core dimension: Platform (job_via).

One row per unique job posting platform/channel.
*/

with base as (
  select nullif(lower(trim(job_via)), '') as job_via
  from {{ ref('stg_raw_jobs') }}
)

select
  md5(job_via) as platform_id,
  job_via as platform_name,
  current_timestamp as created_at
from base
where job_via is not null
group by job_via
