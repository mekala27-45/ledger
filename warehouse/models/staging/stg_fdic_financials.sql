{{ config(tags=['real']) }}
select
    CERT as cert,
    report_date,
    NAME as name,
    STALP as state,
    ASSET as total_assets_thousands,
    DEP as deposits_thousands,
    LNLSNET as net_loans_thousands,
    EQ as equity_thousands,
    NETINC as net_income_ytd_thousands,
    NIMY as nim_pct,
    EEFFR as efficiency_ratio_pct,
    ROA as roa_pct,
    ROE as roe_pct,
    NCLNLSR as noncurrent_loans_pct,
    NTLNLSR as net_charge_offs_pct,
    LNATRESR as allowance_to_loans_pct,
    RBCRWAJ as total_risk_based_capital_pct,
    RBC1AAJ as tier1_to_average_assets_pct
from {{ source('real', 'fdic_financials') }}
