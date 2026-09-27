select txn_id from {{ ref('fct_card_transaction') }} where transaction_date > date '{{ var("as_of_date") }}'
