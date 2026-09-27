-- Denial rate by county and year for the analysis population.
select activity_year, county_fips, count(*) as applications, sum(denied::int) as denials,
    avg(denied::int) as denial_rate
from {{ ref('mart_hmda_applications') }}
where county_fips is not null and county_fips <> 'NA'
group by 1, 2
