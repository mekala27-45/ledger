-- Unadjusted denial rates by year and reported group, for race and ethnicity and for sex.
with g as (
    select activity_year, 'race_ethnicity' as dimension, race_ethnicity_group as grp, denied
    from {{ ref('mart_hmda_applications') }}
    union all
    select activity_year, 'sex', derived_sex, denied
    from {{ ref('mart_hmda_applications') }}
)
select activity_year, dimension, grp as "group", count(*) as applications,
    sum(denied::int) as denials, avg(denied::int) as denial_rate
from g
group by 1, 2, 3
