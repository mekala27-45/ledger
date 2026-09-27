-- What the general ledger system reports as each account's month end balance.
select month, gl_account, {{ money('closing_balance') }} as reported_balance
from {{ source('generated', 'gl_reported_balances') }}
