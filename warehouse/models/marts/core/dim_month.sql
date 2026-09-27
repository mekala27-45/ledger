-- One row per month of the bank's window, with the generator's recession months marked.
select
    m.month,
    m.month_start,
    last_day(m.month_start) as month_end,
    {{ month_index('m.month') }} as month_index,
    cast(year(m.month_start) as varchar) || 'Q' || cast(quarter(m.month_start) as varchar) as quarter,
    year(m.month_start) as year,
    m.is_recession,
    m.unemployment_rate,
    m.policy_rate
from {{ ref('stg_macro_path') }} as m
