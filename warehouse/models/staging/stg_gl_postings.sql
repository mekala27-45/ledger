-- Debits are positive and credits negative, so every transaction and every month sums to zero.
select
    posting_id,
    transaction_id,
    cast(source_type as varchar) as source_type,
    source_id,
    cast(gl_account as varchar) as gl_account,
    {{ money('amount') }} as amount,
    posted_at,
    cast(month as varchar) as month
from {{ source('generated', 'gl_postings') }}
