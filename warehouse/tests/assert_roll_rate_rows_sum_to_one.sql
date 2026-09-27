select month, from_bucket, sum(rate) as total
from {{ ref('mart_roll_rates') }}
group by 1, 2
having abs(sum(rate) - 1) > 1e-9
