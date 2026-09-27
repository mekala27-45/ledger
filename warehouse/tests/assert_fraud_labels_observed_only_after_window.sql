-- A fraud label is observable only once the chargeback window has elapsed.
select txn_id
from {{ ref('fct_card_transaction') }}
where label_observed_by_as_of and transaction_time > timestamp '{{ var("as_of_date") }} 23:59:59' - to_days({{ var('chargeback_window_days') }})
