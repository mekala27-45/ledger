-- The twelve month default outcome for every installment loan originated in the window,
-- under the censoring calendar: a loan's outcome is observed only once twelve months
-- on book have elapsed by the as of month. Unobserved outcomes are null, never zero.
with firsts as (
    select loan_id, min(months_on_book) filter (where enters_default) as months_to_default
    from {{ ref('fct_loan_month') }}
    group by 1
)
select
    l.loan_id,
    l.application_id,
    l.customer_id,
    l.vintage,
    l.origination_month,
    {{ month_index('l.origination_month') }} as origination_index,
    l.principal,
    l.interest_rate,
    f.months_to_default,
    {{ month_index('l.origination_month') }} + {{ var('default_window_months') }}
        <= {{ month_index("'" ~ var('as_of_month') ~ "'") }} as outcome_observed,
    case
        when {{ month_index('l.origination_month') }} + {{ var('default_window_months') }}
            > {{ month_index("'" ~ var('as_of_month') ~ "'") }} then null
        when f.months_to_default is not null and f.months_to_default <= {{ var('default_window_months') }} then 1
        else 0
    end as default_12m
from {{ ref('dim_loan') }} as l
left join firsts as f using (loan_id)
where l.product = 'installment' and not l.back_book
