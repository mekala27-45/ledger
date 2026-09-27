-- Portfolio totals by product and month: balances, delinquency and losses.
select
    product,
    month,
    month_index,
    count(*) filter (where state not in ('charged_off', 'paid_off', 'matured')) as open_loans,
    sum(closing_balance) filter (where state not in ('charged_off', 'paid_off', 'matured')) as balance,
    sum(closing_balance) filter (where state in ('dpd30', 'dpd60', 'dpd90', 'dpd120', 'dpd150')) as balance_30_plus,
    sum(closing_balance) filter (where state in ('dpd90', 'dpd120', 'dpd150')) as balance_90_plus,
    sum(charge_off_amount) as charge_offs,
    sum(recovery_amount) as recoveries,
    sum(interest_paid) + sum(card_interest) as interest
from {{ ref('fct_loan_month') }}
group by 1, 2, 3
