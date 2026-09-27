select gl_account, name, account_type, normal_balance, statement_line,
    case when account_type in ('income', 'expense') then 'income_statement' else 'balance_sheet' end as statement
from {{ ref('stg_gl_chart') }}
