select
    loan_id,
    product,
    application_id,
    origination_date,
    strftime(origination_date, '%Y-%m') as origination_month,
    {{ money('principal') }} as principal,
    interest_rate,
    term_months,
    vintage,
    {{ money('credit_limit') }} as credit_limit,
    customer_id
from {{ source('generated', 'loans') }}
