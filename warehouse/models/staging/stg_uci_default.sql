{{ config(tags=['real']) }}
select * from {{ source('real', 'uci_default') }}
