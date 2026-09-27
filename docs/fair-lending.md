# Fair lending: method, the proxy list, and what the numbers can say

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

This is the method behind the fair lending function, f03, and the `/fair-lending` page. It is written the way a bank's fair lending policy would state its own analysis, with every figure rendered from the manifest.

## The population

The Home Mortgage Disclosure Act loan application register for New Jersey, 215,881 applications from the 646 lenders that reported there in 2024 and 2025. The analysis keeps first lien, closed end, owner occupied home purchase and refinance applications on site built one to four unit homes that reached a credit decision: originated, approved but not accepted, or denied. Withdrawn and incomplete files never reached a decision and are left out, as an examiner would leave them out. 31,050 of them were denied, 14.4%.

Race, ethnicity and sex are HMDA's derived fields, as the applicant reported them. "Not provided" is its own group and is never folded into another.

## Unadjusted disparities

For each group, the denial rate divided by the reference group's: white non Hispanic applicants for race and ethnicity, male applicants for sex. The interval is the log method for a ratio of two proportions. Every comparison in the family is corrected with Benjamini and Hochberg's procedure before it is called a finding; 7 of 8 unadjusted comparisons survive it.

| Dimension | Group | Applications | Denials | Denial rate | Ratio to reference | 95% low | 95% high | BH q value |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| race and ethnicity | Black | 18,550 | 4,448 | 24.0% | 2.24 | 2.17 | 2.31 | 0.0000 |
| race and ethnicity | Not provided | 35,183 | 7,267 | 20.7% | 1.93 | 1.88 | 1.98 | 0.0000 |
| race and ethnicity | Hispanic or Latino | 28,971 | 5,010 | 17.3% | 1.62 | 1.57 | 1.67 | 0.0000 |
| race and ethnicity | Asian | 28,168 | 3,160 | 11.2% | 1.05 | 1.01 | 1.09 | 0.0172 |
| race and ethnicity | White non Hispanic (reference) | 95,397 | 10,214 | 10.7% | not applicable | not applicable | not applicable | not applicable |
| race and ethnicity | Other or joint | 9,612 | 951 | 9.9% | 0.92 | 0.87 | 0.98 | 0.0172 |
| sex | Not provided | 14,014 | 3,866 | 27.6% | 1.74 | 1.69 | 1.80 | 0.0000 |
| sex | Female | 45,462 | 7,258 | 16.0% | 1.01 | 0.98 | 1.04 | 0.5053 |
| sex | Male (reference) | 72,178 | 11,418 | 15.8% | not applicable | not applicable | not applicable | not applicable |
| sex | Joint | 84,227 | 8,508 | 10.1% | 0.64 | 0.62 | 0.66 | 0.0000 |

Source: real:hmda, New Jersey HMDA 2024 and 2025, first lien owner occupied home purchase and refinance applications on 1 to 4 unit homes that reached a decision, as of 2026-08-31.

## Adjusted disparities

A logistic regression of the denial on indicators for each group and the controls the public file allows: the logarithm of income with a flag where income is missing, the logarithm of the loan amount, loan to value in bands, debt to income in HMDA's bands, loan type, loan purpose, the automated underwriting system used, the year, and a fixed effect for each of the 143 lenders with enough applications of both outcomes to estimate one (92.0% of applications), the rest sharing one. The fixed effect means a group is compared with the reference group at the same lender. Missing values are encoded as their own level, never dropped, because dropping them would drop a different share of each group.

| Dimension | Group | Odds ratio | 95% low | 95% high | BH q value | Finding at q < 0.05 |
|---|---|---:|---:|---:|---:|---|
| race and ethnicity | Black | 1.76 | 1.67 | 1.85 | 0.0000 | higher odds of denial |
| race and ethnicity | Hispanic or Latino | 1.42 | 1.36 | 1.49 | 0.0000 | higher odds of denial |
| race and ethnicity | Asian | 1.42 | 1.34 | 1.49 | 0.0000 | higher odds of denial |
| race and ethnicity | Not provided | 1.40 | 1.33 | 1.47 | 0.0000 | higher odds of denial |
| race and ethnicity | Other or joint | 1.09 | 1.00 | 1.19 | 0.0539 | not distinguishable from the reference |
| sex | Not provided | 0.91 | 0.85 | 0.98 | 0.0136 | lower odds of denial |
| sex | Female | 0.88 | 0.84 | 0.91 | 0.0000 | lower odds of denial |
| sex | Joint | 0.76 | 0.73 | 0.79 | 0.0000 | lower odds of denial |

Source: real:hmda, New Jersey HMDA 2024 and 2025, first lien owner occupied home purchase and refinance applications on 1 to 4 unit homes that reached a decision, as of 2026-08-31.

### What adjustment can and cannot tell you

An unadjusted gap is what an applicant experiences and what a journalist will print; an adjusted gap is what remains after the file is taken into account. Examiners look at both. Here the unadjusted odds ratio for Black applicants is 2.63 and the adjusted one 1.76: the controls explain part of the gap and not all of it.

The public file leaves out the two variables a lender's own analysis would control for first: the applicant's credit score and the automated underwriting system's result. Credit history is the first denial reason on 21.0% of denials to Black applicants and 18.3% to white non Hispanic applicants. An adjusted gap in this data is therefore a question to ask of a lender's data, not a finding about any lender, and the page says so beside the table.

Adjustment can also widen a gap. Asian applicants are denied about as often as white non Hispanic applicants before adjustment (a rate ratio of 1.05) but carry an adjusted odds ratio of 1.42: on the controls, their files are stronger, so equal files are denied more often.

## The map

Denial rates by county, unadjusted, and adjusted as observed denials over the denials a model of the controls alone predicts for that county's applications, scaled to the state rate. County is on the proxy list: it is used to draw the map and never enters a model.

| County | Applications | Denial rate | Observed over expected | Adjusted rate |
|---|---:|---:|---:|---:|
| Essex | 15,023 | 18.5% | 1.13 | 16.3% |
| Cumberland | 3,683 | 17.6% | 1.00 | 14.3% |
| Passaic | 8,984 | 16.5% | 1.05 | 15.1% |
| Hudson | 10,059 | 16.2% | 1.31 | 18.8% |
| Atlantic | 6,988 | 16.2% | 1.02 | 14.7% |
| Salem | 2,013 | 16.1% | 1.03 | 14.8% |
| Union | 11,099 | 15.9% | 1.03 | 14.8% |
| Warren | 3,544 | 15.5% | 0.97 | 13.9% |
| Camden | 14,793 | 15.5% | 0.94 | 13.6% |
| Cape May | 2,102 | 15.1% | 0.87 | 12.5% |
| Mercer | 8,859 | 14.8% | 1.02 | 14.6% |
| Middlesex | 18,327 | 14.8% | 1.02 | 14.7% |
| Burlington | 15,196 | 14.3% | 0.95 | 13.7% |
| Sussex | 5,463 | 13.6% | 0.92 | 13.3% |
| Bergen | 18,591 | 13.5% | 1.05 | 15.1% |
| Gloucester | 10,036 | 13.2% | 0.91 | 13.1% |
| Ocean | 18,654 | 13.0% | 0.88 | 12.6% |
| Monmouth | 17,313 | 12.4% | 0.97 | 14.0% |
| Somerset | 8,531 | 11.5% | 0.93 | 13.4% |
| Morris | 12,829 | 11.1% | 0.97 | 13.9% |
| Hunterdon | 3,532 | 10.2% | 0.89 | 12.7% |

## Adverse action reasons

When the bank's own scorecard declines an application, Regulation B requires the specific principal reasons. They are computed the way lenders compute them: for each characteristic, the points the applicant would have earned at that characteristic's best bin less the points they did earn, largest first, at most four, each mapped to a plain language reason in `rules/reason_codes.yaml`. An approved applicant gets none. The engine refuses to explain with any entry on the proxy list, and a test holds it to that.

## The proxy list

`rules/proxies.yaml` lists 32 protected attributes and proxies that no credit or fraud model may use. The reasoning, entry by entry:

- **Race, ethnicity, sex, marital status, religion, national origin, age, receipt of public assistance.** The prohibited bases under the Equal Credit Opportunity Act and Regulation B, in every spelling the data here uses.
- **ZIP code, census tract, county, and latitude and longitude.** Fine resolution geography reproduces a neighbourhood's racial composition closely enough that a model using it can rebuild the prohibited basis. County is kept for the map only.
- **Names.** A name carries sex, and often ethnicity and national origin.
- **Education.** It tracks race and national origin closely enough in public data that keeping it out is the defensible choice.
- **The population of the applicant's city.** A location proxy at a coarser grain.
- **Counts grouped on date of birth.** The BAF suite's count of emails per date of birth depends on how common the applicant's birth year is among applicants, so it carries age. It was the strongest age carrier in the application fraud model until it was listed; `DECISIONS.md` has the challenge.

Every published model's feature list is checked against the list, in the pipeline and in `tests/models/test_proxy_list.py`: 8 models checked, 0 using any entry.

| Model | Features | Protected attributes or proxies among them |
|---|---:|---|
| aml_triage | 13 | none |
| attrition | 18 | none |
| cure | 13 | none |
| fraud_account | 27 | none |
| fraud_card | 18 | none |
| pd_challenger | 13 | none |
| pd_scorecard | 8 | none |
| relief | 5 | none |
