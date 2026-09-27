-- The Federal Reserve's 2026 domestic scenario variables by quarter, with the historic series.
select scenario, quarter, unemployment_rate, real_gdp_growth, house_price_index, treasury_3m, treasury_10y,
    mortgage_rate, bbb_yield, cpi_inflation
from {{ ref('stg_frb_scenarios') }}
