-- The transition matrix pooled over the window, with the bucket order the heatmap uses.
with t as (
    select from_bucket, to_bucket, sum(loans) as loans
    from {{ ref('mart_roll_rates') }}
    group by 1, 2
)
select
    from_bucket,
    to_bucket,
    loans,
    loans / sum(loans) over (partition by from_bucket) as rate,
    case from_bucket when 'current' then 1 when '30' then 2 when '60' then 3 when '90+' then 4 end as from_order,
    case to_bucket when 'current' then 1 when '30' then 2 when '60' then 3 when '90+' then 4
        when 'charged_off' then 5 when 'paid_off' then 6 end as to_order
from t
