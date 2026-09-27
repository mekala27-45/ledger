{{ config(tags=['real']) }}
-- Metadata only. The narrative text is read by the NLP package from the staged file,
-- so the warehouse and everything built from it never carries free text.
select
    complaint_id,
    date_received,
    month,
    product,
    sub_product,
    issue,
    company,
    state,
    submitted_via,
    company_response_to_consumer,
    monetary_relief,
    timely,
    narrative_chars
from {{ source('real', 'cfpb_narratives') }}
