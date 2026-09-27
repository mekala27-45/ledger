select
    loan_id,
    month,
    months_on_book,
    state_open,
    state,
    {{ dpd_bucket('state_open') }} as bucket_open,
    {{ dpd_bucket('state') }} as bucket,
    {{ money('opening_balance') }} as opening_balance,
    {{ money('closing_balance') }} as closing_balance,
    {{ money('scheduled_payment') }} as scheduled_payment,
    {{ money('amount_paid') }} as amount_paid,
    {{ money('interest_paid') }} as interest_paid,
    {{ money('card_purchases') }} as card_purchases,
    {{ money('card_interest') }} as card_interest,
    {{ money('charge_off_amount') }} as charge_off_amount,
    {{ money('recovery_amount') }} as recovery_amount
from {{ source('generated', 'loan_performance') }}
