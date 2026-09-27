{{ config(materialized='view') }}
-- Every posted deposit entry with its account's product and customer.
select
    e.entry_id,
    e.transaction_id,
    e.month,
    e.posted_at,
    e.posted_date,
    e.txn_type,
    e.amount,
    e.branch_id,
    e.reference,
    e.account_id,
    a.customer_id,
    a.product,
    e.counterparty_account_id,
    e.counterparty_id
from {{ ref('stg_deposit_entries') }} as e
join {{ ref('dim_deposit_account') }} as a using (account_id)
