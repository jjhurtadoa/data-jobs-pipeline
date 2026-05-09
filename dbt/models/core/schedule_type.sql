/*
Core dimension: Schedule Type.

One row per unique job schedule type (e.g., Full-time, Part-time, Contract).
*/

select
  md5(job_schedule_type) as schedule_type_id,
  job_schedule_type as schedule_name,
  current_timestamp() as created_at
from {{ ref('stg_raw_jobs') }}
where job_schedule_type is not null
group by job_schedule_type
