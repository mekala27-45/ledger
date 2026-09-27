{{ config(tags=['real']) }}
select * from {{ source('real', 'frb_charge_off_delinquency') }}
