-- Month end balance sheet from the ledger. Presentation sign: assets positive, the
-- allowance negative within assets, liabilities and equity positive. Equity includes
-- earnings to date, because the generated ledger carries no year end closing entry.
with bal as (
    select b.month, b.month_index, g.statement_line, g.account_type,
        sum(b.balance_from_postings) as debit_balance
    from {{ ref('mart_gl_account_month') }} as b
    join {{ ref('dim_gl_account') }} as g using (gl_account)
    group by 1, 2, 3, 4
)
select
    month,
    month_index,
    sum(debit_balance) filter (where statement_line = 'cash') as cash,
    sum(debit_balance) filter (where statement_line = 'securities') as securities,
    sum(debit_balance) filter (where statement_line = 'loans_installment') as loans_installment,
    sum(debit_balance) filter (where statement_line = 'loans_card') as loans_card,
    sum(debit_balance) filter (where statement_line = 'loans_mortgage') as loans_mortgage,
    sum(debit_balance) filter (where statement_line = 'allowance') as allowance,
    sum(debit_balance) filter (where account_type in ('asset', 'contra_asset')) as total_assets,
    -sum(debit_balance) filter (where statement_line = 'deposits_checking') as deposits_checking,
    -sum(debit_balance) filter (where statement_line = 'deposits_savings') as deposits_savings,
    -sum(debit_balance) filter (where statement_line = 'deposits_time') as deposits_time,
    -sum(debit_balance) filter (where statement_line = 'borrowings') as borrowings,
    -sum(debit_balance) filter (where account_type = 'liability') as total_liabilities,
    -sum(debit_balance) filter (where account_type in ('equity', 'income', 'expense')) as total_equity
from bal
group by 1, 2
