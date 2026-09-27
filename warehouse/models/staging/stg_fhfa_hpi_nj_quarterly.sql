{{ config(tags=['real']) }}
select * from {{ source('real', 'fhfa_hpi_nj_quarterly') }}
