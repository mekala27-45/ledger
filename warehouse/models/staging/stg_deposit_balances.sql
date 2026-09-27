-- closing_balance is rebuilt from posted entries by the contracts stage; the
-- figure the core system reported is kept beside it for the data quality page.
select
    account_id,
    cast(month as varchar) as month,
    {{ money('opening_balance') }} as opening_balance,
    {{ money('closing_balance') }} as closing_balance,
    {{ money('closing_balance_reported') }} as closing_balance_reported,
    balance_rolls,
    closed_this_month
from {{ source('generated', 'deposit_balances') }}
