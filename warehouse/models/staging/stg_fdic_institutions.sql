{{ config(tags=['real']) }}
select * from {{ source('real', 'fdic_institutions') }}
