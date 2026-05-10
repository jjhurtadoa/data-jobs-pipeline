{% test dates_not_future(model, column_name) %}

select count(*) as future_dates
from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} > current_timestamp
having count(*) > 0

{% endtest %}
