-- The fair lending analysis population: first lien, closed end, owner occupied home
-- purchase and refinance applications for site built one to four unit homes that
-- reached a decision (originated, approved not accepted, or denied). Withdrawn and
-- incomplete files never reached a credit decision and are excluded, as examiners do.
select
    activity_year,
    lei,
    county_fips,
    derived_race,
    derived_ethnicity,
    derived_sex,
    applicant_age_band,
    action_taken,
    denied,
    loan_type,
    loan_purpose,
    occupancy_type,
    loan_amount,
    loan_to_value_ratio,
    income,
    dti_band,
    aus_1,
    denial_reason_1,
    case
        when derived_ethnicity = 'Hispanic or Latino' then 'Hispanic or Latino'
        when derived_race = 'Black or African American' then 'Black'
        when derived_race = 'Asian' then 'Asian'
        when derived_race = 'White' and derived_ethnicity = 'Not Hispanic or Latino' then 'White non Hispanic'
        when derived_race in ('Race Not Available') or derived_ethnicity in ('Ethnicity Not Available') then 'Not provided'
        else 'Other or joint'
    end as race_ethnicity_group
from {{ ref('stg_hmda_lar') }}
where lien_status = '1'
    and coalesce(open_end_line, '2') = '2'
    and coalesce(business_purpose, '2') = '2'
    and occupancy_type = 1
    and loan_purpose in (1, 31, 32)
    and derived_dwelling_category = 'Single Family (1-4 Units):Site-Built'
    and action_taken in (1, 2, 3)
