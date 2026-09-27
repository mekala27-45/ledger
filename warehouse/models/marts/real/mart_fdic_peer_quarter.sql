-- Quarterly ratios for real FDIC insured institutions in the seven state region. The peer
-- group used on the executive page (by asset size) is chosen in function 1 from this mart.
select
    cert,
    name,
    state,
    report_date,
    cast(year(report_date) as varchar) || 'Q' || cast(quarter(report_date) as varchar) as quarter,
    total_assets_thousands,
    deposits_thousands,
    net_loans_thousands,
    equity_thousands,
    nim_pct,
    efficiency_ratio_pct,
    roa_pct,
    roe_pct,
    noncurrent_loans_pct,
    net_charge_offs_pct,
    allowance_to_loans_pct,
    total_risk_based_capital_pct,
    tier1_to_average_assets_pct,
    net_loans_thousands / nullif(deposits_thousands, 0) as loans_to_deposits
from {{ ref('stg_fdic_financials') }}
