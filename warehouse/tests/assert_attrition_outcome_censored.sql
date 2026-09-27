select customer_id, month
from {{ ref('mart_customer_month') }}
where month_index + 12 > {{ month_index("'" ~ var('as_of_month') ~ "'") }} and closes_within_12m is not null
