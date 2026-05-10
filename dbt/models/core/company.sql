/*
Core dimension: Company.

One row per unique company. Sourced from deduplicated job postings.
No business logic; just a canonical list of companies.
*/

select
  md5(company_name_clean) as company_id,
  company_name_clean as company_name,
  current_timestamp as created_at
from (
  select nullif(lower(trim(company_name)), '') as company_name_clean
  from {{ ref('stg_raw_jobs') }}
) s
where company_name_clean is not null
group by company_name_clean
