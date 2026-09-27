-- One row per customer with a checking account per month end: what the bank knew at that
-- month end, and whether the primary checking account closed in the next twelve months.
-- The outcome is null when twelve months have not elapsed by the as of month.
with checking as (
    select account_id, customer_id, open_date, closed_month
    from {{ ref('dim_deposit_account') }}
    where product = 'checking'
),
bal as (
    select c.customer_id, b.month, {{ month_index('b.month') }} as month_index,
        b.closing_balance as checking_balance, c.closed_month, c.open_date
    from {{ ref('stg_deposit_balances') }} as b
    join checking as c using (account_id)
    where not b.closed_this_month
),
other as (
    select a.customer_id, b.month, sum(b.closing_balance) as other_balance
    from {{ ref('stg_deposit_balances') }} as b
    join {{ ref('dim_deposit_account') }} as a using (account_id)
    where a.product <> 'checking'
    group by 1, 2
),
fees as (
    select customer_id, month, count(*) as fee_count, sum(-amount) as fee_amount,
        count(*) filter (where txn_type = 'FEE_OVERDRAFT') as overdraft_count
    from {{ ref('fct_deposit_entry') }}
    where txn_type in ('FEE_MAINTENANCE', 'FEE_OVERDRAFT')
    group by 1, 2
),
flows as (
    select customer_id, month,
        sum(amount) filter (where amount > 0) as inflow,
        -sum(amount) filter (where amount < 0) as outflow,
        count(*) as entries,
        count(*) filter (where txn_type = 'PAYROLL_IN') as payroll_credits
    from {{ ref('fct_deposit_entry') }}
    where product = 'checking'
    group by 1, 2
)
select
    b.customer_id,
    b.month,
    b.month_index,
    b.checking_balance,
    coalesce(o.other_balance, 0) as other_balance,
    b.checking_balance - lag(b.checking_balance, 3) over (partition by b.customer_id order by b.month_index)
        as checking_change_3m,
    coalesce(f.fee_count, 0) as fee_count,
    coalesce(f.overdraft_count, 0) as overdraft_count,
    coalesce(fl.inflow, 0) as inflow,
    coalesce(fl.outflow, 0) as outflow,
    coalesce(fl.entries, 0) as entries,
    coalesce(fl.payroll_credits, 0) as payroll_credits,
    date_diff('month', b.open_date, last_day(cast(b.month || '-01' as date))) as checking_tenure_months,
    case
        when b.month_index + 12 > {{ month_index("'" ~ var('as_of_month') ~ "'") }} then null
        when b.closed_month is not null and {{ month_index('b.closed_month') }} > b.month_index
            and {{ month_index('b.closed_month') }} <= b.month_index + 12 then 1
        else 0
    end as closes_within_12m
from bal as b
left join other as o using (customer_id, month)
left join fees as f using (customer_id, month)
left join flows as fl using (customer_id, month)
