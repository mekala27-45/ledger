{{ config(tags=['real']) }}
select * from {{ source('real', 'macro_monthly') }}
