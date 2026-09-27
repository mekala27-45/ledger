-- Cumulative default rate by origination quarter and months on book. A vintage's curve
-- stops at the last month on book every one of its loans has reached by the as of date.
with base as (
    select vintage, count(*) as loans, sum(principal) as principal, max(origination_index) as last_origination
    from {{ ref('mart_loan_outcomes') }}
    group by 1
),
defaults as (
    select vintage, months_to_default as mob, count(*) as defaults
    from {{ ref('mart_loan_outcomes') }}
    where months_to_default is not null
    group by 1, 2
),
grid as (
    select b.vintage, b.loans, b.principal, g.mob
    from base as b
    cross join range(0, 36) as g(mob)
    where b.last_origination + g.mob <= {{ month_index("'" ~ var('as_of_month') ~ "'") }}
)
select
    grid.vintage,
    grid.mob as months_on_book,
    grid.loans,
    grid.principal,
    sum(coalesce(d.defaults, 0)) over (partition by grid.vintage order by grid.mob) as cumulative_defaults,
    sum(coalesce(d.defaults, 0)) over (partition by grid.vintage order by grid.mob) / grid.loans as cumulative_default_rate
from grid
left join defaults as d on d.vintage = grid.vintage and d.mob = grid.mob
