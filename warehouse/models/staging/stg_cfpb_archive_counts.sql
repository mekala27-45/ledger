{{ config(tags=['real']) }}
select * from {{ source('real', 'cfpb_archive_counts') }}
