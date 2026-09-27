-- Customers with the attributes a bank lawfully holds for its own analytics. Race and
-- sex are not here; they exist only in the HMDA style application records.
with products as (
    select customer_id,
        count(*) filter (where product = 'checking') as checking_accounts,
        count(*) filter (where product = 'savings') as savings_accounts,
        count(*) filter (where product = 'time') as time_accounts
    from {{ ref('stg_deposit_accounts') }}
    group by 1
),
loans as (
    select customer_id,
        count(*) filter (where product = 'card') as card_accounts,
        count(*) filter (where product = 'installment') as installment_loans,
        count(*) filter (where product = 'mortgage') as mortgages
    from {{ ref('stg_loans') }}
    group by 1
)
select
    c.customer_id,
    c.open_date,
    c.birth_year,
    2026 - c.birth_year as age_at_as_of,
    case
        when 2026 - c.birth_year < 25 then '18 to 24'
        when 2026 - c.birth_year < 35 then '25 to 34'
        when 2026 - c.birth_year < 50 then '35 to 49'
        when 2026 - c.birth_year < 65 then '50 to 64'
        else '65 and over'
    end as age_band,
    c.state,
    c.county_fips,
    c.segment,
    c.annual_income,
    c.home_branch,
    c.digital_active,
    c.complaint_flag,
    date_diff('month', c.open_date, date '{{ var("as_of_date") }}') as tenure_months,
    coalesce(p.checking_accounts, 0) as checking_accounts,
    coalesce(p.savings_accounts, 0) as savings_accounts,
    coalesce(p.time_accounts, 0) as time_accounts,
    coalesce(l.card_accounts, 0) as card_accounts,
    coalesce(l.installment_loans, 0) as installment_loans,
    coalesce(l.mortgages, 0) as mortgages,
    (coalesce(p.checking_accounts, 0) > 0)::int + (coalesce(p.savings_accounts, 0) > 0)::int
        + (coalesce(p.time_accounts, 0) > 0)::int + (coalesce(l.card_accounts, 0) > 0)::int
        + (coalesce(l.installment_loans, 0) > 0)::int + (coalesce(l.mortgages, 0) > 0)::int as product_types_held
from {{ ref('stg_customers') }} as c
left join products as p using (customer_id)
left join loans as l using (customer_id)
