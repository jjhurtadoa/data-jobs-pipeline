/*
Core dimension: Schedule Type.

One row per unique job schedule type (e.g., Full-time, Part-time, Contract).
*/

with base as (
  select nullif(lower(trim(job_schedule_type)), '') as job_schedule_type
  from {{ ref('stg_raw_jobs') }}
)

select
  md5(job_schedule_type) as schedule_type_id,
  job_schedule_type as schedule_name,
  current_timestamp as created_at
from base
where job_schedule_type is not null
group by job_schedule_type
