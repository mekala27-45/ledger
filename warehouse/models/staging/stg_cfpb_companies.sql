{{ config(tags=['real']) }}
select * from {{ source('real', 'cfpb_companies') }}
