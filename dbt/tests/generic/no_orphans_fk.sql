{% test no_orphans_fk(model, column_name, to, to_column, foreign_key_column=None) %}

{% set fk_col = foreign_key_column if foreign_key_column is not none else column_name %}

with model_keys as (
  select distinct {{ fk_col }} as fk_value
  from {{ model }}
  where {{ fk_col }} is not null
),
ref_keys as (
  select distinct {{ to_column }} as ref_value
  from {{ to }}
)
select mk.fk_value
from model_keys mk
left join ref_keys rk
  on mk.fk_value = rk.ref_value
where rk.ref_value is null

{% endtest %}
