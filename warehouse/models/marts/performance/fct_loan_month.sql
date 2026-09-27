-- One row per loan per month on the books, with delinquency buckets in order.
select
    p.loan_id,
    l.product,
    l.vintage,
    l.origination_month,
    l.back_book,
    p.month,
    {{ month_index('p.month') }} as month_index,
    p.months_on_book,
    p.state_open,
    p.state,
    p.bucket_open,
    p.bucket,
    p.opening_balance,
    p.closing_balance,
    p.scheduled_payment,
    p.amount_paid,
    p.interest_paid,
    p.card_purchases,
    p.card_interest,
    p.charge_off_amount,
    p.recovery_amount,
    p.state in ('dpd90', 'dpd120', 'dpd150') as is_90_plus,
    p.state in ('dpd90', 'dpd120', 'dpd150', 'charged_off') and p.state_open not in ('dpd90', 'dpd120', 'dpd150', 'charged_off')
        as enters_default
from {{ ref('stg_loan_performance') }} as p
join {{ ref('dim_loan') }} as l using (loan_id)
