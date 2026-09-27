# Validation report: Probability of default scorecard (champion)

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `pd_scorecard` |
| Purpose | Rank and price installment loan applications by twelve month default risk and state the reasons for a decline |
| Tier | 1: Material: informs a credit, fraud or regulatory decision directly |
| Role | champion |
| Status | in use |
| Owner | Head of analytics |
| Prediction time | The application date, before any loan exists |
| Outcome | 90 days past due or charge off within 12 months of origination |
| Last validated | 2026-08-31 |
| Conclusion | **approved with conditions** |

## Purpose and scope

The scorecard decides installment loan applications at Harborline: it ranks each
application by the probability of default within 12
months, approves at or above a score of 580, and states the
reasons for every decline. It also supplies the probability of default used in expected
loss. It is the champion; `pd_challenger` is shadow scored beside it.

In scope: consumer installment loan applications through every channel. Out of scope:
cards and mortgages, which it has never seen, and any use as a pricing model without a
separate calibration.


## Conceptual soundness

A weight of evidence scorecard is the method most consumer lenders still use for
application decisions, for reasons that hold here: each characteristic's effect is
monotone and visible in a table, the model is a logistic regression a reviewer can
reproduce by hand, and the points give Regulation B reasons directly, as the
characteristics where an applicant earned the fewest points against the best
attainable. The alternatives considered were a logistic regression on raw
characteristics, which ranks about as well but gives no natural reason codes, and a
gradient boosted model, which is the challenger.

Each characteristic is fine classed into up to 20 quantile bins,
then coarse classed until every bin holds at least 5% of
applicants and weight of evidence is monotone. Characteristics enter only above an
information value of 0.02 and below a weight of evidence correlation of
0.7 with any stronger one; a characteristic whose sign reverses
in the joint fit is removed. Points are scaled to 600 at odds of
30 to one, with 20 points to double the odds. Of
13 candidates, 8 were kept:

| characteristic | iv | kept |
|---|---:|---|
| revolving_utilization | 0.333 | kept |
| bureau_score | 0.310 | kept |
| dti | 0.233 | kept |
| employment_months | 0.074 | kept |
| oldest_trade_months | 0.069 | kept |
| purpose | 0.045 | kept |
| inquiries_6m | 0.030 | kept |
| loan_amount | 0.024 | kept |
| annual_income | 0.011 | information value 0.0113 below the floor |
| housing_status | 0.009 | information value 0.0087 below the floor |
| term_months | 0.008 | information value 0.0084 below the floor |
| delinquencies_24m | 0.004 | information value 0.0036 below the floor |
| channel | 0.002 | information value 0.0021 below the floor |


## Data and assumptions

Generated data: installment loan applications to the fictional bank from its core
banking generator, with the application record as it stood on the application date.
The outcome is 90 days past due or charge off within 12 months of origination. Under the censoring calendar only loans
originated at least 12 months before the as of date have
an outcome; later ones are excluded, never counted as good. The split is by
origination month: development 5,721 loans, validation
3,725, test 3,742. The validation months are the two
vintages written under a loosened cutoff; the test months include the recession quarter.

Declined applicants have no outcome, so the scorecard is fitted on booked loans only.
No reject inference was applied; the effect is that the scorecard's view of the lowest
score bands rests on the applicants a legacy policy chose to book.

Age, ZIP code and county are held on the application for the fairness audit and are
on the committed proxy list; none is a candidate characteristic.

Before any figure here was trusted, the pipeline recovered the generator's stated
parameters:

| parameter | stated | estimate | interval_low | interval_high | tolerance | within |
|---|---:|---:|---:|---:|---:|---|
| Latent risk rank order (Spearman; perfect ordering is 1) | 1.000 | 0.775 | 0.775 | 0.775 | 0.600 | true |
| Latent risk coefficient | 0.950 | 0.913 | 0.863 | 0.963 | 0.150 | true |
| Macro sensitivity per point of unemployment | 0.300 | 0.322 | 0.271 | 0.373 | 0.100 | true |
| Loose vintage effect | 0.450 | 0.459 | 0.387 | 0.532 | 0.150 | true |
| Deposit beta, checking | 0.020 | 0.020 | 0.020 | 0.020 | 0.010 | true |
| Deposit beta, savings | 0.380 | 0.380 | 0.380 | 0.380 | 0.030 | true |
| Deposit beta, time | 0.720 | 0.720 | 0.720 | 0.720 | 0.030 | true |
| Recovery share at 24 months, installment | 0.220 | 0.204 | 0.204 | 0.204 | 0.050 | true |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.


## Development evidence

The fitted scorecard:

| characteristic | bin | share | bad_rate | woe | points |
|---|---|---:|---:|---:|---:|
| revolving_utilization | (-inf, 0.0697] | 5.0% | 1.05% | 1.331 | 96.1 |
| revolving_utilization | (0.0697, 0.1322] | 10.0% | 1.40% | 1.038 | 91.3 |
| revolving_utilization | (0.1322, 0.1832] | 10.0% | 1.92% | 0.715 | 86.1 |
| revolving_utilization | (0.1832, 0.3486] | 30.0% | 2.86% | 0.307 | 79.4 |
| revolving_utilization | (0.3486, 0.48] | 20.0% | 4.29% | -0.113 | 72.5 |
| revolving_utilization | (0.48, 0.5197] | 5.0% | 4.88% | -0.249 | 70.3 |
| revolving_utilization | (0.5197, 0.6275] | 10.0% | 6.65% | -0.578 | 64.9 |
| revolving_utilization | (0.6275, +inf] | 10.0% | 8.39% | -0.829 | 60.9 |
| bureau_score | (-inf, 672] | 5.3% | 8.55% | -0.850 | 60.9 |
| bureau_score | (672, 694] | 15.4% | 6.48% | -0.549 | 65.7 |
| bureau_score | (694, 716] | 19.7% | 4.53% | -0.170 | 71.7 |
| bureau_score | (716, 747] | 24.9% | 3.73% | 0.032 | 74.9 |
| bureau_score | (747, 763] | 10.4% | 2.01% | 0.666 | 84.9 |
| bureau_score | (763, 795] | 14.4% | 1.71% | 0.835 | 87.6 |
| bureau_score | (795, +inf] | 10.0% | 1.23% | 1.170 | 92.9 |
| dti | (-inf, 0.1193] | 10.0% | 1.22% | 1.174 | 96.2 |
| dti | (0.1193, 0.1672] | 10.0% | 2.27% | 0.544 | 84.5 |
| dti | (0.1672, 0.2117] | 15.0% | 2.56% | 0.420 | 82.2 |
| dti | (0.2117, 0.2491] | 15.0% | 3.04% | 0.244 | 78.9 |
| dti | (0.2491, 0.2713] | 10.0% | 3.32% | 0.154 | 77.2 |
| dti | (0.2713, 0.2843] | 5.0% | 4.88% | -0.249 | 69.8 |
| dti | (0.2843, +inf] | 35.0% | 5.95% | -0.459 | 65.9 |
| employment_months | (-inf, 15] | 5.9% | 6.19% | -0.502 | 62.7 |
| employment_months | (15, 25] | 9.4% | 5.21% | -0.319 | 66.9 |
| employment_months | (25, 71] | 40.1% | 4.05% | -0.055 | 73.1 |
| employment_months | (71, 206] | 34.6% | 3.39% | 0.132 | 77.5 |
| employment_months | (206, +inf] | 10.0% | 1.92% | 0.713 | 91.1 |
| oldest_trade_months | (-inf, 77] | 10.3% | 6.25% | -0.511 | 69.3 |
| oldest_trade_months | (77, 95] | 10.2% | 4.78% | -0.227 | 72.1 |
| oldest_trade_months | (95, 134] | 24.9% | 4.00% | -0.042 | 74.0 |
| oldest_trade_months | (134, 150] | 9.7% | 3.79% | 0.015 | 74.5 |
| oldest_trade_months | (150, 170] | 10.3% | 3.41% | 0.126 | 75.6 |
| oldest_trade_months | (170, 196] | 9.9% | 3.00% | 0.256 | 76.9 |
| oldest_trade_months | (196, +inf] | 24.7% | 2.83% | 0.316 | 77.5 |
| purpose | home_improvement | 15.8% | 4.76% | -0.223 | 67.7 |
| purpose | auto | 25.7% | 4.28% | -0.111 | 71.1 |
| purpose | other | 8.2% | 3.82% | 0.006 | 74.6 |
| purpose | debt_consolidation | 37.5% | 3.73% | 0.031 | 75.3 |
| purpose | major_purchase | 12.8% | 2.19% | 0.579 | 91.6 |
| inquiries_6m | (-inf, 1] | 73.4% | 3.45% | 0.111 | 75.3 |
| inquiries_6m | (1, 2] | 18.4% | 4.76% | -0.222 | 72.6 |
| inquiries_6m | (2, +inf] | 8.3% | 5.30% | -0.335 | 71.7 |
| loan_amount | (-inf, 5,600] | 10.1% | 2.78% | 0.335 | 83.2 |
| loan_amount | (5,600, 14,100] | 55.1% | 3.62% | 0.063 | 76.1 |
| loan_amount | (14,100, 15,200] | 5.1% | 3.81% | 0.011 | 74.7 |
| loan_amount | (15,200, +inf] | 29.8% | 4.63% | -0.194 | 69.3 |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

On the development sample the scorecard's AUROC is 0.722; on
validation 0.666. Its scores move very little between development
and test (population stability index 0.0032).


## Outcomes analysis on held out data

On the out of time test sample (3,742 loans, 254
defaults) the scorecard reaches an AUROC of 0.662 (Gini
0.324, KS 0.238). At the cutoff it approves
80.3% of test applicants.

Calibration is where it falls short. The mean predicted default rate on the test months
is 3.93% against an observed 6.79%, and on the
validation months 4.44% against 9.61%.
The ranking holds; the level does not, because the loosened vintages and the recession
raised default for reasons no application characteristic carries. The known parameter
recovery above attributes it: the vintage effect and the macro sensitivity are both
present and both outside the scorecard.

By applicant age band on the test sample (age is never an input):

| Group | N | Event rate | Mean score | Calibration gap | Auroc | Approval rate | Adverse impact ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| 18 to 24 | 492 | 6.71% | 3.83% | -2.9% | 0.590 | 82.3% | 1.00 |
| 25 to 34 | 611 | 7.04% | 4.20% | -2.8% | 0.658 | 78.4% | 0.95 |
| 35 to 49 | 1,238 | 6.87% | 4.00% | -2.9% | 0.708 | 78.8% | 0.96 |
| 50 to 64 | 988 | 6.98% | 3.76% | -3.2% | 0.652 | 81.7% | 0.99 |
| 65 and over | 413 | 5.81% | 3.84% | -2.0% | 0.634 | 81.8% | 0.99 |

The adverse impact ratio compares each band's approval rate with the most approved band.


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 375 | 0.54% | 2.13% |
| 2 | 375 | 1.03% | 3.20% |
| 3 | 374 | 1.52% | 4.81% |
| 4 | 374 | 2.09% | 4.55% |
| 5 | 374 | 2.76% | 5.35% |
| 6 | 374 | 3.53% | 6.42% |
| 7 | 374 | 4.42% | 7.49% |
| 8 | 374 | 5.56% | 6.95% |
| 9 | 374 | 7.11% | 10.70% |
| 10 | 374 | 10.75% | 16.31% |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

## Benchmarking

Against the base rate, a logistic regression on the same raw characteristics, and the
gradient boosted challenger, all on the same test sample. The challenger's case for
promotion is in its own report.

The same machinery on real data, 30,000 credit card accounts from the UCI Default of
Credit Card Clients dataset (Yeh and Lien (2009), CC BY 4.0), split at random because the
data has no dates:

| measure | generated | uci |
|---|---|---|
| Loans or accounts with an outcome | 13,188 | 30,000 |
| Default rate | 6.3% | 22.1% |
| Characteristics kept | 8 | 7 |
| Scorecard AUROC, test | 0.662 | 0.768 |
| Scorecard Gini, test | 0.324 | 0.536 |
| Challenger AUROC, test | 0.667 | 0.788 |
| Logistic AUROC, test | 0.668 | 0.750 |
| Scorecard calibration error, test | 0.0286 | 0.0125 |

The real accounts' scorecard:

| characteristic | bin | share | bad_rate | woe | points |
|---|---|---:|---:|---:|---:|
| pay_status_1 | (-inf, -2] | 9.3% | 12.30% | 0.706 | 91.9 |
| pay_status_1 | (-2, 0] | 68.3% | 14.12% | 0.547 | 88.5 |
| pay_status_1 | (0, 1] | 12.1% | 34.71% | -0.627 | 63.5 |
| pay_status_1 | (1, +inf] | 10.4% | 68.81% | -2.050 | 33.1 |
| pay_status_3 | (-inf, -1] | 33.2% | 16.80% | 0.341 | 81.0 |
| pay_status_3 | (-1, 0] | 52.6% | 17.27% | 0.308 | 80.6 |
| pay_status_3 | (0, +inf] | 14.2% | 52.63% | -1.364 | 60.3 |
| pay_amt_1 | (-inf, 0] | 17.1% | 36.32% | -0.697 | 66.7 |
| pay_amt_1 | (0, 1,000] | 8.6% | 23.33% | -0.069 | 75.8 |
| pay_amt_1 | (1,000, 2,000] | 22.0% | 22.63% | -0.030 | 76.4 |
| pay_amt_1 | (2,000, 3,615] | 17.2% | 21.36% | 0.045 | 77.5 |
| pay_amt_1 | (3,615, 4,370] | 5.0% | 20.00% | 0.127 | 78.7 |
| pay_amt_1 | (4,370, 6,245] | 10.0% | 16.11% | 0.391 | 82.5 |
| pay_amt_1 | (6,245, 8,015] | 5.0% | 14.78% | 0.493 | 84.0 |
| pay_amt_1 | (8,015, 18,224] | 10.0% | 14.72% | 0.498 | 84.1 |
| pay_amt_1 | (18,224, +inf] | 5.0% | 8.00% | 1.184 | 94.1 |
| limit_bal | (-inf, 20,000] | 8.3% | 36.22% | -0.693 | 68.1 |
| limit_bal | (20,000, 30,000] | 5.4% | 36.18% | -0.691 | 68.1 |
| limit_bal | (30,000, 70,000] | 17.3% | 27.66% | -0.298 | 73.1 |
| limit_bal | (70,000, 100,000] | 10.6% | 24.88% | -0.154 | 74.9 |
| limit_bal | (100,000, 140,000] | 9.2% | 23.01% | -0.051 | 76.2 |
| limit_bal | (140,000, 160,000] | 5.9% | 17.75% | 0.275 | 80.3 |
| limit_bal | (160,000, 200,000] | 11.2% | 17.26% | 0.309 | 80.8 |
| limit_bal | (200,000, 240,000] | 8.8% | 17.00% | 0.327 | 81.0 |
| limit_bal | (240,000, 360,000] | 15.2% | 14.86% | 0.487 | 83.0 |
| limit_bal | (360,000, +inf] | 8.2% | 11.08% | 0.824 | 87.3 |
| payment_ratio_avg | (-inf, 0.03451] | 9.7% | 34.48% | -0.617 | 71.8 |
| payment_ratio_avg | (0.03451, 0.07259] | 33.8% | 25.54% | -0.189 | 75.3 |
| payment_ratio_avg | (0.07259, 0.1296] | 9.6% | 23.21% | -0.063 | 76.3 |
| payment_ratio_avg | (0.1296, 0.3005] | 9.6% | 16.82% | 0.340 | 79.7 |
| payment_ratio_avg | (0.3005, 0.6116] | 9.7% | 15.77% | 0.416 | 80.3 |
| payment_ratio_avg | (0.6116, 1] | 14.5% | 14.93% | 0.482 | 80.8 |
| payment_ratio_avg | (1, +inf] | 9.6% | 14.00% | 0.556 | 81.4 |
| payment_ratio_avg | missing | 3.5% | 36.06% | -0.686 | 71.2 |
| bill_growth_6m | (-inf, -0.0493] | 20.0% | 29.61% | -0.393 | 72.9 |
| bill_growth_6m | (-0.0493, -0.02985] | 5.0% | 26.78% | -0.253 | 74.3 |
| bill_growth_6m | (-0.02985, 0] | 19.0% | 23.52% | -0.080 | 76.0 |
| bill_growth_6m | (0, 0.006685] | 6.0% | 19.11% | 0.184 | 78.7 |
| bill_growth_6m | (0.006685, +inf] | 50.0% | 18.48% | 0.225 | 79.1 |
| utilization_1 | (-inf, 0.2205] | 45.0% | 18.17% | 0.246 | 77.0 |
| utilization_1 | (0.2205, 0.4258] | 10.0% | 20.40% | 0.103 | 76.9 |
| utilization_1 | (0.4258, 0.526] | 5.0% | 23.22% | -0.063 | 76.8 |
| utilization_1 | (0.526, 0.6302] | 5.0% | 25.44% | -0.184 | 76.7 |
| utilization_1 | (0.6302, 0.9827] | 25.0% | 26.24% | -0.226 | 76.7 |
| utilization_1 | (0.9827, 1.013] | 5.0% | 27.56% | -0.292 | 76.6 |
| utilization_1 | (1.013, +inf] | 5.0% | 30.56% | -0.438 | 76.5 |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.662 | 0.324 | 0.0626 | 0.0286 |
| Base rate | 0.500 | 0.000 | 0.0641 | 0.0307 |
| Logistic on raw characteristics | 0.668 | 0.336 | 0.0624 | 0.0285 |
| Challenger (GBM) | 0.667 | 0.334 | 0.0624 | 0.0279 |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

## Limitations

- The data is generated. The scorecard proves the method and the controls, not a
  real portfolio's risk.
- Fitted on booked loans only, with no reject inference.
- Through the cycle by construction: it does not move with unemployment or with
  underwriting changes, which is why calibration fails on later vintages.
- The UCI comparison uses a random split, so it cannot show drift, and the UCI data
  is a Taiwanese card portfolio two decades old, not a US installment book.
- Simplified: no bureau attributes beyond the handful the generator produces.


## Ongoing monitoring plan

Monthly, on every application and on each vintage as its outcomes mature:


| Measure | Trigger | Action |
|---|---|---|
| Score PSI, monthly applications against development | above 0.1 warns, above 0.25 breaches | Investigate the shift; revalidate on breach |
| Characteristic stability index, each characteristic | above 0.25 | Review the characteristic's bins |
| Rolling test AUROC as outcomes mature | falls 0.03 below the validation figure | Redevelop |
| Observed over predicted default by vintage | outside 0.8 to 1.25 for two vintages | Recalibrate the intercept or apply an overlay |

## Effective challenge

Challenges raised during development and what each changed, from `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-26 | On the validation months the scorecard's mean predicted default rate sat well under the observed rate, while its rank ordering held up. | The validation months are the two vintages written under the loosened cutoff, and the test months carry the recession quarter. The hazard fit recovers a vintage effect close to the generator's stated one, and no application characteristic carries it, so a scorecard fitted on earlier vintages cannot see it. That is a calibration problem, not a ranking problem, and a bank would treat it the same way: keep the scorecard for decisions and adjust the probability used for loss. | Calibration became a non critical gate, so the report concludes approved with a stated condition rather than approved, and expected loss in function 2 applies an observed to expected overlay by vintage instead of the raw scorecard probability. |
| 2026-09-26 | The fitted scorecard has no delinquency characteristic. Delinquencies in the last 24 months fell under the information value floor and were dropped. | In this book the characteristic is nearly empty (most applicants have none) and carries little information once the bureau score is in the model, which already reflects payment history. Forcing it in would add a characteristic whose bins barely differ, and whose points would move with noise. | The published information value table now lists every candidate with the reason it was kept or dropped, so a reviewer sees the decision instead of an absence, and the challenger, which sees every candidate, confirms the characteristic adds little. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Recovers the generator's latent risk ordering (Spearman) | at least 0.4 | 0.7754 | pass |
| Test AUROC at or above the floor | at least 0.62 | 0.6618 | pass |
| Test AUROC no more than 0.02 below the logistic benchmark | at least -0.02 | -0.0063 | pass |
| Score stability, development to test (PSI) | at most 0.25 | 0.0032 | pass |
| Lowest adverse impact ratio across age bands | at least 0.8 | 0.9524 | pass |
| Point in time recompute of sampled rows | at least 200 | 200.0000 | pass |
| Expected calibration error on test | at most 0.02 | 0.0286 | FAIL |

## Validation conclusion

The scorecard ranks risk soundly out of time, recovers the generator's risk ordering,
is stable, and passes the age band audit. It under predicts the level of default on
the loosened and recession vintages. For decisions, which depend on rank, it is fit for
use. For expected loss, its probability is used only with the vintage overlay in
the lending function, and recalibration is the condition below.

The adverse action reasons it produced for declined test month applicants, by the
first reason given:

| reason | declines | share |
|---|---:|---:|
| Proportion of balances to credit limits on revolving accounts is too high | 1,539 | 61.1% |
| Credit history reported by the credit bureau is insufficient or delinquent | 680 | 27.0% |
| Income insufficient for amount of credit requested | 284 | 11.3% |
| Length of employment | 14 | 0.6% |


**approved with conditions.** Conditions:

| Condition |
|---|
| Remediate before the next validation: Expected calibration error on test (measured 0.02859) |

## The integration contract

| Line | What this model does |
|---|---|
| trained | On loans originated in the first twelve months of the window, with outcomes observed under the censoring calendar. |
| timed | Scores the application as submitted; a leakage test recomputes 200 sampled rows from the application record. |
| calibrated | Points convert back to the logistic probability exactly; calibration on later vintages is reported, not assumed. |
| useful | Benchmarked on the out of time test sample against the base rate, a logistic model on raw characteristics and the challenger. |
| fair | Approval rates, AUROC and calibration by applicant age band; age is never an input. |
| gated | Promoted only after every gate in its validation report passed or was accepted with a stated condition. |
| served | POST /v1/scorecard/score in the API; in the browser from the published scorecard table on /studio. |
| integrated | Sets the approve or decline decision at the stated cutoff and supplies expected loss in function 2. |
| monitored | Score PSI and characteristic stability monthly; rolling AUROC and calibration as twelve month outcomes arrive. |
| documented | This validation report, the scorecard table, and docs/models.md. |
| bounded | Scores installment loan applications only; it has never seen a card or mortgage application. |
| validated | This report, rendered from the manifest before the model is used anywhere. |
| explainable | Every decline returns up to four adverse action reasons, the largest point shortfalls, in plain words. |
