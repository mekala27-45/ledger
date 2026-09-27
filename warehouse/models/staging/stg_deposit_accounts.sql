select
    account_id,
    customer_id,
    product,
    open_date,
    term_months,
    interest_bearing,
    closed_month
from {{ source('generated', 'deposit_accounts') }}
