{{ config(tags=['stream']) }}
select
    txn_id,
    card_key,
    transaction_time,
    category,
    {{ money('amount') }} as amount,
    merchant_key,
    merchant_lat,
    merchant_long,
    customer_lat,
    customer_long,
    city_pop,
    state,
    gender,
    birth_year,
    is_fraud
from {{ source('sparkov', 'card_transactions') }}
