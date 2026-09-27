-- One row per month with every component the executive ratios are built from. The
-- ratios themselves live in the metric layer (metrics/bank.yaml), never here, so each
-- is defined once and computed the same way at every grain.
with npl as (
    select month, sum(balance_90_plus) as nonperforming_loans, sum(balance) as gross_loans
    from {{ ref('mart_portfolio_monthly') }}
    group by 1
)
select
    b.month,
    b.month_index,
    m.quarter,
    m.year,
    b.cash,
    b.securities,
    b.loans_installment,
    b.loans_card,
    b.loans_mortgage,
    b.loans_installment + b.loans_card + b.loans_mortgage as total_loans,
    -b.allowance as allowance,
    b.total_assets,
    b.deposits_checking,
    b.deposits_savings,
    b.deposits_time,
    b.deposits_checking + b.deposits_savings + b.deposits_time as total_deposits,
    b.borrowings,
    b.total_liabilities,
    b.total_equity,
    b.securities + b.loans_installment + b.loans_card + b.loans_mortgage as earning_assets,
    i.interest_income_loans,
    i.interest_income_securities,
    i.interest_expense_deposits,
    i.interest_expense_borrowings,
    i.noninterest_income,
    i.provision,
    i.noninterest_expense,
    i.tax,
    i.net_income,
    coalesce(n.nonperforming_loans, 0) as nonperforming_loans
from {{ ref('mart_balance_sheet_monthly') }} as b
join {{ ref('mart_income_statement_monthly') }} as i using (month)
join {{ ref('dim_month') }} as m using (month)
left join npl as n using (month)
