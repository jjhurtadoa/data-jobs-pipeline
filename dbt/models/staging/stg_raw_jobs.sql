/*
Staging model: normalize and deduplicate raw job postings.

This model:
1. Casts and normalizes columns from raw.jobs
2. Computes a business key hash (excluding job_skills and job_type_skills)
3. Deduplicates by business key for non-skill columns, preserving the first (earliest ingested) record
4. Aggregates and deduplicates skill data across all duplicates with the same business key
5. Aggregates job_skills and job_type_skills using JSONB-native operations

The business key ensures that the same job posting (same company, title, location, date, etc.)
appearing multiple times with different skill lists is collapsed to a single row with
the union of all skills.
*/

with raw_data as (
  select
    id as raw_job_id,
    job_title_short,
    job_title,
    job_location,
    job_via,
    job_schedule_type,
    job_work_from_home,
    search_location,
    job_posted_date,
    job_no_degree_mention,
    job_health_insurance,
    job_country,
    salary_rate,
    salary_year_avg,
    salary_hour_avg,
    company_name,
    job_skills,
    job_type_skills,
    ingested_at,
    md5(
      concat_ws(
        '||',
        coalesce(lower(trim(company_name)), ''),
        coalesce(lower(trim(job_title)), ''),
        coalesce(lower(trim(job_location)), ''),
        coalesce(lower(trim(job_posted_date)), ''),
        coalesce(lower(trim(job_schedule_type)), ''),
        coalesce(lower(trim(job_via)), ''),
        coalesce(cast(salary_year_avg as varchar), ''),
        coalesce(cast(salary_hour_avg as varchar), ''),
        coalesce(cast(job_work_from_home as varchar), ''),
        coalesce(cast(job_no_degree_mention as varchar), ''),
        coalesce(cast(job_health_insurance as varchar), ''),
        coalesce(lower(trim(job_country)), ''),
        coalesce(lower(trim(salary_rate)), '')
      )
    ) as business_key
  from raw.jobs
),

ranked as (
  select
    *,
    row_number() over (
      partition by business_key
      order by ingested_at asc, raw_job_id asc
    ) as dedup_rank
  from raw_data
),

primary_records as (
  select * from ranked where dedup_rank = 1
),

-- Parse and aggregate job_skills from all duplicate records
job_skills_tokens as (
  select
    rd.business_key,
    trim(skill_item.skill_name) as skill_name
  from raw_data rd
  cross join lateral jsonb_array_elements_text(coalesce(rd.job_skills, '[]'::jsonb)) as skill_item(skill_name)
  where trim(skill_item.skill_name) != ''
),

aggregated_job_skills as (
  select
    business_key,
    array_agg(distinct skill_name order by skill_name) as aggregated_job_skills
  from job_skills_tokens
  group by business_key
),

-- Parse and aggregate job_type_skills (category -> [skills]) across duplicates
job_type_pairs as (
  select
    rd.business_key,
    trim(category_item.skill_category) as skill_category,
    trim(skill_item.skill_name) as skill_name
  from raw_data rd
  cross join lateral jsonb_each(coalesce(rd.job_type_skills, '{}'::jsonb)) as category_item(skill_category, skills_json)
  cross join lateral jsonb_array_elements_text(
    case
      when jsonb_typeof(category_item.skills_json) = 'array' then category_item.skills_json
      when category_item.skills_json is null then '[]'::jsonb
      else jsonb_build_array(category_item.skills_json)
    end
  ) as skill_item(skill_name)
  where trim(category_item.skill_category) != ''
    and trim(skill_item.skill_name) != ''
),

job_type_category_agg as (
  select
    business_key,
    skill_category,
    array_agg(distinct skill_name order by skill_name) as skills_array
  from job_type_pairs
  group by business_key, skill_category
),

aggregated_job_type_skills as (
  select
    business_key,
    jsonb_object_agg(skill_category, to_jsonb(skills_array)) as aggregated_job_type_skills
  from (
    select
      business_key,
      skill_category,
      skills_array
    from job_type_category_agg
    order by business_key, skill_category
  ) ordered_category_skills
  group by business_key
)

select
  pr.raw_job_id,
  pr.business_key,
  pr.job_title_short,
  pr.job_title,
  pr.job_location,
  pr.job_via,
  pr.job_schedule_type,
  pr.job_work_from_home,
  pr.search_location,
  pr.job_posted_date,
  pr.job_no_degree_mention,
  pr.job_health_insurance,
  pr.job_country,
  pr.salary_rate,
  pr.salary_year_avg,
  pr.salary_hour_avg,
  pr.company_name,
  coalesce(ajs.aggregated_job_skills, array[]::text[]) as job_skills_array,
  coalesce(ajts.aggregated_job_type_skills, coalesce(pr.job_type_skills, '{}'::jsonb)) as job_type_skills,
  pr.ingested_at,
  current_timestamp as dbt_processed_at
from primary_records pr
left join aggregated_job_skills ajs on pr.business_key = ajs.business_key
left join aggregated_job_type_skills ajts on pr.business_key = ajts.business_key
