{{ config(tags=['stream']) }}
-- The card stream as the desk sees it, with when each label becomes observable under
-- the chargeback window. Features that depend on a card's history are computed in
-- packages/desk strictly from prior transactions, not here.
select
    t.txn_id,
    t.card_key,
    t.transaction_time,
    cast(t.transaction_time as date) as transaction_date,
    strftime(t.transaction_time, '%Y-%m') as month,
    hour(t.transaction_time) as hour,
    isodow(t.transaction_time) as weekday,
    t.category,
    t.amount,
    t.merchant_key,
    t.merchant_lat,
    t.merchant_long,
    t.customer_lat,
    t.customer_long,
    2 * 6371.0 * asin(sqrt(
        pow(sin(radians(t.merchant_lat - t.customer_lat) / 2), 2)
        + cos(radians(t.customer_lat)) * cos(radians(t.merchant_lat))
          * pow(sin(radians(t.merchant_long - t.customer_long) / 2), 2)
    )) as distance_km,
    t.city_pop,
    t.state,
    t.gender,
    t.birth_year,
    t.is_fraud,
    t.transaction_time + to_days({{ var('chargeback_window_days') }}) as label_observable_at,
    t.transaction_time + to_days({{ var('chargeback_window_days') }})
        <= timestamp '{{ var("as_of_date") }} 23:59:59' as label_observed_by_as_of
from {{ ref('stg_card_transactions') }} as t
