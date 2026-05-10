with staging_keys as (
  select business_key
  from {{ ref('stg_raw_jobs') }}
  where nullif(trim(company_name), '') is not null
),
posting_keys as (
  select business_key
  from {{ ref('job_posting') }}
)
select
  sk.business_key
from staging_keys sk
left join posting_keys pk on sk.business_key = pk.business_key
where pk.business_key is null
