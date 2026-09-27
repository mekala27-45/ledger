select
    entry_id,
    transaction_id,
    cast(month as varchar) as month,
    posted_at,
    cast(posted_at as date) as posted_date,
    cast(txn_type as varchar) as txn_type,
    {{ money('amount') }} as amount,
    branch_id,
    nullif(reference, -1) as reference,
    account_id,
    counterparty_account_id,
    counterparty_id
from {{ source('generated', 'deposit_entries') }}
