-- Complaints received per month by product, from the Bureau's aggregations.
select month, product, complaints
from {{ ref('stg_cfpb_volume_by_product') }}
