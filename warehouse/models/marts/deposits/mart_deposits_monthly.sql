-- Deposit balances, accounts, openings and closings by product and month.
select
    a.product,
    b.month,
    {{ month_index('b.month') }} as month_index,
    count(*) as accounts,
    sum(b.closing_balance) as balance,
    count(*) filter (where strftime(a.open_date, '%Y-%m') = b.month) as opened,
    count(*) filter (where b.closed_this_month) as closed
from {{ ref('stg_deposit_balances') }} as b
join {{ ref('dim_deposit_account') }} as a using (account_id)
group by 1, 2, 3
