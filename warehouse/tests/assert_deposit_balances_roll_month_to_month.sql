-- Once rebuilt from entries, every account's opening balance equals last month's closing balance.
select account_id, month
from (
    select account_id, month, opening_balance,
        lag(closing_balance) over (partition by account_id order by month) as previous_closing
    from {{ ref('stg_deposit_balances') }}
)
where previous_closing is not null and opening_balance <> previous_closing
