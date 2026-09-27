-- Month end totals from the sub ledgers, by the ledger control account they must tie to.
-- Deposits come from account balances rebuilt from posted entries; loans from the
-- servicing system's month end balances for open loans.
with deposits as (
    select a.gl_account, b.month, -sum(b.closing_balance) as subledger_debit_balance, count(*) as accounts
    from {{ ref('stg_deposit_balances') }} as b
    join {{ ref('dim_deposit_account') }} as a using (account_id)
    group by 1, 2
),
loans as (
    select l.gl_account, p.month, sum(p.closing_balance) as subledger_debit_balance, count(*) as accounts
    from {{ ref('stg_loan_performance') }} as p
    join {{ ref('dim_loan') }} as l using (loan_id)
    where p.state not in ('charged_off', 'paid_off', 'matured')
    group by 1, 2
)
select gl_account, month, subledger_debit_balance::decimal(18, 2) as subledger_debit_balance, accounts, 'deposits' as subledger
from deposits
union all
select gl_account, month, subledger_debit_balance::decimal(18, 2), accounts, 'loans'
from loans
