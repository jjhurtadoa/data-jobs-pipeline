/*
Core dimension: Salary Rate Type.

One row per unique salary rate type (e.g., 'year', 'hour', 'month').
This is a controlled vocabulary; values come from the raw data.
*/

select
  md5(salary_rate) as rate_type_id,
  salary_rate as rate_name,
  current_timestamp() as created_at
from {{ ref('stg_raw_jobs') }}
where salary_rate is not null
group by salary_rate
