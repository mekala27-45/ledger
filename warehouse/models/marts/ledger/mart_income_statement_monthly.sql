-- Monthly income statement from the ledger's income and expense postings, income positive.
with flows as (
    select b.month, b.month_index, g.statement_line, -sum(b.posted) as amount
    from {{ ref('mart_gl_account_month') }} as b
    join {{ ref('dim_gl_account') }} as g using (gl_account)
    where g.account_type in ('income', 'expense')
    group by 1, 2, 3
)
select
    month,
    month_index,
    coalesce(sum(amount) filter (where statement_line = 'interest_income_loans'), 0) as interest_income_loans,
    coalesce(sum(amount) filter (where statement_line = 'interest_income_securities'), 0) as interest_income_securities,
    -coalesce(sum(amount) filter (where statement_line = 'interest_expense_deposits'), 0) as interest_expense_deposits,
    -coalesce(sum(amount) filter (where statement_line = 'interest_expense_borrowings'), 0) as interest_expense_borrowings,
    coalesce(sum(amount) filter (where statement_line = 'noninterest_income'), 0) as noninterest_income,
    -coalesce(sum(amount) filter (where statement_line = 'provision'), 0) as provision,
    -coalesce(sum(amount) filter (where statement_line = 'noninterest_expense'), 0) as noninterest_expense,
    -coalesce(sum(amount) filter (where statement_line = 'tax'), 0) as tax,
    coalesce(sum(amount), 0) as net_income
from flows
group by 1, 2
