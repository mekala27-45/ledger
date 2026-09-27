select
    a.account_id,
    a.customer_id,
    a.product,
    a.open_date,
    a.term_months,
    a.interest_bearing,
    a.closed_month,
    case a.product when 'checking' then '2000' when 'savings' then '2010' when 'time' then '2020' end as gl_account
from {{ ref('stg_deposit_accounts') }} as a
