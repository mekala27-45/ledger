{{ config(tags=['real']) }}
select * from {{ source('real', 'baf') }}
