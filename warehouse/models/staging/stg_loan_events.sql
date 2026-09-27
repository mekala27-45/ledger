select
    event_id,
    loan_id,
    month,
    event_type,
    {{ money('amount') }} as amount,
    posted_date,
    is_payoff,
    link_id
from {{ source('generated', 'loan_events') }}
