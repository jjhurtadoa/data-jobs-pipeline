/*
Core dimension: Country.

One row per unique country. Sourced from deduplicated job postings.
*/

with base as (
  select nullif(lower(trim(job_country)), '') as job_country
  from {{ ref('stg_raw_jobs') }}
)

select
  md5(job_country) as country_id,
  job_country as country_name,
  current_timestamp as created_at
from base
where job_country is not null
group by job_country
