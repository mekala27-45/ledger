# Validation report: Probability of default challenger (monotone GBM)

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `pd_challenger` |
| Purpose | Test whether a gradient boosted model beats the scorecard enough to justify its opacity |
| Tier | 1: Informs a decision a person makes, with a method whose behaviour is hard to inspect |
| Role | challenger |
| Status | validated |
| Owner | Head of analytics |
| Prediction time | The application date |
| Outcome | 90 days past due or charge off within 12 months of origination |
| Last validated | 2026-08-31 |
| Conclusion | **not approved** |

## Purpose and scope

The challenger exists to answer one question for the model risk function: would a
gradient boosted model decide installment loan applications better enough than the
scorecard to justify giving up the scorecard's transparency? It is shadow scored on
every application, including declines, and decides nothing.


## Conceptual soundness

LightGBM on the same raw characteristics the scorecard considered, with monotone
constraints on every numeric characteristic in the direction the scorecard's weight of
evidence runs, so a higher bureau score can never raise predicted risk and a higher
utilisation can never lower it. Categorical characteristics are unconstrained. Early
stopped on the validation months, 132 trees. Without the constraints a
tree model can learn non monotone effects that a lender could not defend to an examiner
or explain to an applicant.


## Data and assumptions

Identical to the champion's: the same booked loans, the same censoring, the same split
by origination month, the same leakage test and the same exclusion of every protected
attribute and proxy.


## Development evidence

Development AUROC 0.776, validation 0.670.
Its rank order agrees with the champion's on every application at a Spearman correlation
of 0.962, so the two models mostly disagree at the margin rather than
about who is risky.


## Outcomes analysis on held out data

On the test sample the challenger's AUROC is 0.667, an improvement of
0.005 over the champion. Stability from development to test is
0.0035. By age band, at the threshold that approves the champion's share
of applicants:

| Group | N | Event rate | Mean score | Calibration gap | Auroc | Approval rate | Adverse impact ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| 18 to 24 | 492 | 6.71% | 3.90% | -2.8% | 0.625 | 18.3% | 0.91 |
| 25 to 34 | 611 | 7.04% | 4.33% | -2.7% | 0.663 | 19.8% | 0.99 |
| 35 to 49 | 1,238 | 6.87% | 4.08% | -2.8% | 0.708 | 18.1% | 0.90 |
| 50 to 64 | 988 | 6.98% | 3.81% | -3.2% | 0.650 | 20.0% | 1.00 |
| 65 and over | 413 | 5.81% | 3.83% | -2.0% | 0.651 | 19.9% | 0.99 |


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 375 | 0.85% | 2.93% |
| 2 | 375 | 1.15% | 3.20% |
| 3 | 374 | 1.51% | 3.74% |
| 4 | 374 | 1.99% | 5.35% |
| 5 | 374 | 2.59% | 4.81% |
| 6 | 374 | 3.38% | 6.15% |
| 7 | 374 | 4.43% | 6.42% |
| 8 | 374 | 5.72% | 7.49% |
| 9 | 374 | 7.47% | 7.75% |
| 10 | 374 | 10.90% | 20.05% |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

## Benchmarking

Against the champion first, then the logistic model and the base rate, on the same test
sample.


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.667 | 0.334 | 0.0624 | 0.0279 |
| Champion scorecard | 0.662 | 0.324 | 0.0626 | 0.0286 |
| Logistic on raw characteristics | 0.668 | 0.336 | 0.0624 | 0.0285 |
| Base rate | 0.500 | 0.000 | 0.0641 | 0.0307 |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

## Limitations

- Cannot produce Regulation B reasons on its own; reasons would have to come from a
  separate explanation method, and a bank would have to validate that method too.
- Shares every limitation of the champion's data.


## Ongoing monitoring plan

While it stays in shadow:


| Measure | Trigger | Action |
|---|---|---|
| Rank agreement with the champion | below 0.7 | Investigate before any promotion case |

## Effective challenge

From `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-26 | The first fit's development AUROC was far above its validation AUROC. | With fifteen leaves and a small minimum leaf, the trees were learning the development months' noise; early stopping alone did not close the gap. | Seven leaves and a minimum of 150 loans per leaf. The development to validation gap narrowed and the validation and test AUROC held. |
| 2026-09-26 | The challenger's test AUROC is above the champion's. | The gain has to pay for what the bank gives up. A gradient boosted model cannot state Regulation B reasons directly; declined applicants would still get reasons computed from the scorecard, which means explaining one model's decision with another model. A small gain does not buy that. | Promotion requires a test AUROC at least 0.01 above the champion's, stated as a gate in the validation report, together with the stability and age band gates. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Test AUROC at least 0.01 above the champion | at least 0.01 | 0.0054 | FAIL |
| Score stability, development to test (PSI) | at most 0.25 | 0.0035 | pass |
| Lowest adverse impact ratio across age bands at the champion's approval rate | at least 0.8 | 0.9029 | pass |
| Expected calibration error on test | at most 0.02 | 0.0279 | FAIL |
| Rank agreement with the champion on every application (Spearman) | at least 0.7 | 0.9617 | pass |

## Validation conclusion

Not approved for promotion. The challenger is at least as stable and as fair as the
champion and ranks marginally better, but the improvement is under the materiality
margin set before evaluation, and it would cost the bank directly stated adverse action
reasons. It stays in shadow and is re-evaluated at the next validation.


**not approved.** Conditions:

| Condition |
|---|
| Test AUROC at least 0.01 above the champion (measured 0.00535) |

## The integration contract

| Line | What this model does |
|---|---|
| trained | Same development sample as the champion, early stopped on the validation months. |
| timed | Same application record as the champion, under the same leakage test. |
| calibrated | Reported on the out of time test sample beside the champion's calibration. |
| useful | Judged only against the champion, on the same test sample, by a stated materiality margin. |
| fair | The same age band audit, at the threshold that approves the champion's share of applicants. |
| gated | Promotion requires every gate in this report; it has not been promoted. |
| served | Shadow scored in batch on every application, including declines; not served for decisions. |
| integrated | Its scores sit beside the champion's in the applications table for the comparison and nothing else. |
| monitored | Rank agreement with the champion and its own stability, monthly, while it remains in shadow. |
| documented | This validation report and docs/models.md. |
| bounded | Not used for any decision while in shadow; cannot produce Regulation B reasons without a separate explanation method. |
| validated | This report, rendered from the manifest. |
| explainable | Monotone constraints keep each characteristic's effect in the scorecard's direction; feature contributions are published, but adverse action reasons still come from the champion. |
