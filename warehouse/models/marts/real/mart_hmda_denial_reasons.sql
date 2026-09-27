-- The first denial reason reported, by year, for denied applications in the population.
select activity_year,
    case denial_reason_1
        when '1' then 'Debt to income ratio' when '2' then 'Employment history'
        when '3' then 'Credit history' when '4' then 'Collateral'
        when '5' then 'Insufficient cash' when '6' then 'Unverifiable information'
        when '7' then 'Credit application incomplete' when '8' then 'Mortgage insurance denied'
        when '9' then 'Other' else 'Not reported'
    end as reason,
    count(*) as denials
from {{ ref('mart_hmda_applications') }}
where denied
group by 1, 2
