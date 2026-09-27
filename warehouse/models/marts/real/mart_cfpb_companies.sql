-- The companies with the most complaints in the window, as the Bureau publishes them.
select company, complaints, monetary_relief, non_monetary_relief, explanation, in_progress, timely, top_product,
    monetary_relief / complaints as monetary_relief_share,
    timely / complaints as timely_share
from {{ ref('stg_cfpb_companies') }}
