select txn_id from {{ ref('fct_card_transaction') }} where distance_km < 0 or distance_km > 20000
