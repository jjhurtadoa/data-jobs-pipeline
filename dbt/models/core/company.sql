/*
Core dimension: Company.

One row per unique company. Sourced from deduplicated job postings.
No business logic; just a canonical list of companies.
*/

select
  md5(company_name) as company_id,
  company_name,
  current_timestamp() as created_at
from {{ ref('stg_raw_jobs') }}
group by company_name
