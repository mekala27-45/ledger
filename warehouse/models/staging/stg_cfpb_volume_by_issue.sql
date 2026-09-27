{{ config(tags=['real']) }}
select * from {{ source('real', 'cfpb_volume_by_issue') }}
