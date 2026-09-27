{{ config(tags=['real']) }}
select * from {{ source('real', 'frb_scenarios') }}
