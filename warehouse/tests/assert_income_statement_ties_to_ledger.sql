-- Net income for the window equals the negative of every income and expense posting.
with a as (select sum(net_income) as ni from {{ ref('mart_income_statement_monthly') }}),
b as (
    select -sum(p.amount) as ni
    from {{ ref('stg_gl_postings') }} as p
    join {{ ref('dim_gl_account') }} as g using (gl_account)
    where g.statement = 'income_statement'
)
select * from a, b where a.ni <> b.ni
