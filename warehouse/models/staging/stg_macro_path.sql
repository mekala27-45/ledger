select month, month_start, unemployment_rate, policy_rate, ten_year_yield, hpi_growth_annualised, hpi_index, is_recession
from {{ source('generated', 'macro_path') }}
