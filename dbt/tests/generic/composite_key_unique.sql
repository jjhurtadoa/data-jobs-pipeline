{% test composite_key_unique(model, column_names) %}

select
  {% for col in column_names -%}
    {{ col }}{{ "," if not loop.last }}
  {%- endfor %},
  count(*) as duplicate_count
from {{ model }}
group by
  {% for col in column_names -%}
    {{ col }}{{ "," if not loop.last }}
  {%- endfor %}
having count(*) > 1

{% endtest %}
