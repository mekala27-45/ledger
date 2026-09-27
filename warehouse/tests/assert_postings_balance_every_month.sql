-- Double entry: every month's postings sum to zero, to the cent.
select month, sum(amount) as imbalance
from {{ ref('stg_gl_postings') }}
group by 1
having sum(amount) <> 0
