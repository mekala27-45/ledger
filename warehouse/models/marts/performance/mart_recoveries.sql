-- Cumulative recoveries after charge off, as a share of the amount charged off, by
-- months since charge off. The loss given default assumption in function 2 is read here.
with co as (
    select loan_id, product, min(month_index) as co_index, sum(charge_off_amount) as charged_off
    from {{ ref('fct_loan_month') }}
    where charge_off_amount > 0
    group by 1, 2
),
rec as (
    select f.loan_id, f.month_index - co.co_index as months_since, sum(f.recovery_amount) as recovered
    from {{ ref('fct_loan_month') }} as f
    join co using (loan_id)
    where f.recovery_amount > 0
    group by 1, 2
),
grid as (
    select co.product, g.m as months_since, count(*) as loans, sum(co.charged_off) as charged_off
    from co
    cross join range(0, 25) as g(m)
    where co.co_index + g.m <= {{ month_index("'" ~ var('as_of_month') ~ "'") }}
    group by 1, 2
),
cum as (
    select co.product, g.m as months_since, sum(coalesce(r.recovered, 0)) as recovered
    from co
    cross join range(0, 25) as g(m)
    left join rec as r on r.loan_id = co.loan_id and r.months_since <= g.m
    where co.co_index + g.m <= {{ month_index("'" ~ var('as_of_month') ~ "'") }}
    group by 1, 2
)
select grid.product, grid.months_since, grid.loans, grid.charged_off, cum.recovered,
    cum.recovered / nullif(grid.charged_off, 0) as recovery_rate
from grid
join cum using (product, months_since)
