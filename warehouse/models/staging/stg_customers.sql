select
    customer_id,
    open_date,
    birth_year,
    state,
    county_fips,
    segment,
    annual_income,
    home_branch,
    digital_active,
    complaint_flag
from {{ source('generated', 'customers') }}
