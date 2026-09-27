-- The censoring calendar: no loan whose twelve months have not elapsed carries an outcome,
-- and every loan whose window has elapsed carries one.
select loan_id
from {{ ref('mart_loan_outcomes') }}
where (not outcome_observed and default_12m is not null)
   or (outcome_observed and default_12m is null)
