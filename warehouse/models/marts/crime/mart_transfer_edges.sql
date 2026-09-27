-- Money movement between parties: internal transfers between Harborline accounts and
-- person to person payments and wires to and from outside parties. The network and the
-- rapid movement, mule and round tripping rules read this.
select
    e.entry_id,
    e.posted_at,
    e.posted_date,
    e.txn_type,
    abs(e.amount) as amount,
    case when e.amount < 0 then e.account_id else coalesce(e.counterparty_account_id, e.counterparty_id) end as source_party,
    case when e.amount < 0 then coalesce(e.counterparty_account_id, e.counterparty_id) else e.account_id end as target_party,
    e.account_id,
    e.customer_id,
    e.amount > 0 as inbound
from {{ ref('fct_deposit_entry') }} as e
where e.txn_type in ('INTERNAL_TRANSFER', 'P2P_IN', 'P2P_OUT', 'WIRE_IN', 'WIRE_OUT', 'ACH_IN', 'ACH_OUT')
    and (e.counterparty_account_id is not null or e.counterparty_id is not null)
    -- an internal transfer posts two legs; the outbound leg alone describes the edge
    and not (e.txn_type = 'INTERNAL_TRANSFER' and e.amount > 0)
