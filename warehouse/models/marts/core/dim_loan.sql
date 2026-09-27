-- Every loan and card account. Installment loans carry the application they came from.
select
    l.loan_id,
    l.product,
    l.application_id,
    l.origination_date,
    l.origination_month,
    l.principal,
    l.interest_rate,
    l.term_months,
    l.vintage,
    l.credit_limit,
    l.customer_id,
    case l.product when 'installment' then '1200' when 'card' then '1210' when 'mortgage' then '1220' end as gl_account,
    l.origination_date < date '2023-09-01' as back_book,
    a.bureau_score,
    a.channel,
    a.purpose
from {{ ref('stg_loans') }} as l
left join {{ ref('stg_loan_applications') }} as a using (application_id)
