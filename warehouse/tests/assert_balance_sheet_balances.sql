-- Assets equal liabilities plus equity at every month end.
select month, total_assets, total_liabilities, total_equity
from {{ ref('mart_balance_sheet_monthly') }}
where total_assets <> total_liabilities + total_equity
