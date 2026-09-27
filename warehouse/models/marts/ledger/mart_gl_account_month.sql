-- Each ledger account's activity and balance by month, three ways: the sum of the
-- month's postings, the running balance those postings imply, and the balance the
-- ledger system reported. The reconciliation compares them to the cent.
with activity as (
    select gl_account, month, sum(amount) as posted, count(*) as postings
    from {{ ref('stg_gl_postings') }}
    group by 1, 2
),
grid as (
    select g.gl_account, m.month, m.month_index
    from {{ ref('dim_gl_account') }} as g
    cross join {{ ref('dim_month') }} as m
)
select
    grid.gl_account,
    grid.month,
    grid.month_index,
    coalesce(a.postings, 0) as postings,
    coalesce(a.posted, 0)::decimal(18, 2) as posted,
    sum(coalesce(a.posted, 0)) over (partition by grid.gl_account order by grid.month_index)::decimal(18, 2)
        as balance_from_postings,
    r.reported_balance
from grid
left join activity as a using (gl_account, month)
left join {{ ref('stg_gl_reported_balances') }} as r using (gl_account, month)
