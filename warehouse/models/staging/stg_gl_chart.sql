select gl_account, name, account_type, normal_balance, statement_line
from {{ source('generated', 'gl_chart') }}
