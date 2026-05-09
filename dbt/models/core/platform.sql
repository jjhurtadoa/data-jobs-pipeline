/*
Core dimension: Platform (job_via).

One row per unique job posting platform/channel.
*/

select
  md5(job_via) as platform_id,
  job_via as platform_name,
  current_timestamp() as created_at
from {{ ref('stg_raw_jobs') }}
where job_via is not null
group by job_via
