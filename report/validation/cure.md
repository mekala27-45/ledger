# Validation report: Cure within ninety days for delinquent loans

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `cure` |
| Purpose | Order the collections queue by the balance likely to be lost without a call: balance times the probability the loan does not cure |
| Tier | 2: Informs a decision a person makes; moderate materiality |
| Role | sole |
| Status | in use |
| Owner | Head of analytics |
| Prediction time | Each month end, for loans thirty or more days past due; features use that month and earlier |
| Outcome | The loan is current, or paid off, at one of the next three month ends |
| Last validated | 2026-08-31 |
| Conclusion | **approved** |

## Purpose and scope

Order the collections queue by the balance the bank is likely to lose without a call:
each past due loan's balance times the probability it does not return to current within
ninety days. The model informs whom a collector calls first; it never changes terms or
charges anything off, so it is tier two.

Out of scope: hardship programmes, settlement offers, and the decision to charge off.


## Conceptual soundness

Whether a delinquent loan cures depends on how late it is, how long it has been late,
whether the borrower paid anything last month, and the loan itself. Two candidates were
fitted on the same features, a gradient boosted classifier and a logistic regression; the
champion was chosen on held out loans in the validation months, and the boosted model had
to beat the logistic by 0.005 of AUROC to earn its complexity. The model is
the logistic regression (0.760 for LightGBM against
0.762 for the logistic regression on held out loans).

The benchmark that matters is the rule collectors use today, the bucket: each bucket's
training cure rate used as a score.


## Data and assumptions

Every loan thirty or more days past due at a month end. The outcome is whether it is
current or paid off at one of the next three month ends, so it is known three months
later, and the split respects that: training on month ends September 2023 to June 2025, validation on
month ends July to September 2025, test on month ends December 2025 to May 2026 (8,104
delinquent loan months, 2,663 of them cured).

A leakage test recomputed the run of late months, the earlier delinquency episodes and
last month's payment for 200 sampled loan months from the loan's
own history and matched every one. No demographic attribute is a feature.


## Development evidence

Development AUROC 0.784, validation 0.777.
What moves the score most (standardised coefficients for a logistic regression, share of
gain for a boosted model):

| feature | weight |
|---|---:|
| months in a row past due | -0.98 |
| interest rate | -0.61 |
| a card account | 0.29 |
| ninety or more days past due | -0.24 |
| a mortgage | -0.13 |
| sixty days past due | -0.09 |
| earlier delinquencies | -0.08 |
| card utilisation | 0.06 |
| share of the payment made last month | 0.06 |
| made a payment last month | 0.06 |
| balance | -0.05 |
| age of the loan | 0.04 |
| unemployment | 0.01 |


## Outcomes analysis on held out data

On the test months the model reaches an AUROC of 0.787, against
0.761 for the bucket rule and 0.785 for the
LightGBM.

By bucket, on the test months:

| Group | N | Event rate | Mean score | Calibration gap | Auroc |
|---|---:|---:|---:|---:|---:|
| 30 | 3,069 | 58.52% | 57.40% | -1.1% | 0.598 |
| 60 | 1,845 | 30.08% | 32.38% | +2.3% | 0.545 |
| 90+ | 3,190 | 9.78% | 10.40% | +0.6% | 0.638 |

Source: generated, Harborline installment, card and mortgage loans past due at a month end, September 2023 to August 2026, seed 20260831, as of 2026-08-31.


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 811 | 3.42% | 4.07% |
| 2 | 811 | 6.99% | 8.63% |
| 3 | 811 | 12.22% | 11.84% |
| 4 | 811 | 18.36% | 16.28% |
| 5 | 810 | 27.17% | 26.79% |
| 6 | 810 | 35.84% | 32.35% |
| 7 | 810 | 45.46% | 45.31% |
| 8 | 810 | 54.33% | 53.95% |
| 9 | 810 | 60.44% | 60.25% |
| 10 | 810 | 67.90% | 69.26% |

Source: generated, Harborline installment, card and mortgage loans past due at a month end, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Benchmarking

Against the base rate, the bucket rule and the candidate that was not chosen, on the test months:


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.787 | 0.573 | 0.1718 | 0.0107 |
| Base rate | 0.500 | 0.000 | 0.2209 | 0.0266 |
| The bucket rule | 0.761 | 0.523 | 0.1753 | 0.0217 |
| LightGBM on the same features | 0.785 | 0.569 | 0.1723 | 0.0137 |

Source: generated, Harborline installment, card and mortgage loans past due at a month end, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Limitations

- The generator decides cures from a stated process with the loan's latent risk in it.
  Real cures depend on things no loan file holds: a new job, a family emergency, a
  collector's tone.
- A call changes the outcome it predicts. Once the queue is worked in this order, the
  realised cure rates are no longer a clean measure of the model.
- Paid off counts as cured. It is rare from delinquency here, and a real bank might
  treat a payoff through refinancing elsewhere differently.


## Ongoing monitoring plan

Monthly:


| Measure | Trigger | Action |
|---|---|---|
| Realised cure rate by queue decile, monthly | the top decile cures more often than the bottom | Refit |
| Score PSI, monthly against validation | above 0.25 | Revalidate |
| The bucket rule's AUROC beside the model's | the margin falls below the gate for a quarter | Revalidate |

## Effective challenge

From `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-27 | A loan thirty days past due cures far more often than one ninety days past due. A model that only learned the bucket would beat the base rate comfortably and add nothing a collections supervisor does not already do by working the thirty day list first. | The base rate is the wrong benchmark for this model. The benchmark is the rule in use: each bucket's cure rate from the training months, applied as a score. | The bucket rule is a benchmark in the report, and a critical gate requires the model's test AUROC to beat the rule's by two hundredths. Cure rates by bucket are published beside the model's so the rule's strength is visible. |
| 2026-09-27 | A loan that is past due in June and July 2025 appears in the last training month and the first validation month, with nearly the same features and the same outcome. Early stopping and the choice between the two candidates were being made on loans the fit had already seen. | The attrition model memorised customers for the same reason. Month ends are not independent draws when the unit is a loan that stays delinquent for months. | One loan in five is held out of the fit by a hash of its identifier, and early stopping and the choice of champion use only held out loans in the validation months. The test months begin three months after validation ends, so every outcome used to fit or choose the model was known before the first test month end, and a check in the trainer refuses to run otherwise. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Test AUROC above the bucket rule the collections team uses today | at least 0.02 | 0.0251 | pass |
| Test AUROC against the other candidate's (the choice on validation must not cost more than a hundredth) | at least -0.01 | 0.0019 | pass |
| Test AUROC at or above the floor | at least 0.7 | 0.7866 | pass |
| Point in time recompute of sampled delinquent loan months | at least 200 | 200.0000 | pass |
| Expected calibration error on test | at most 0.05 | 0.0107 | pass |

## Validation conclusion

The model orders the queue the way its purpose asks and beats the rule in use on months
it never saw. It is approved for ordering the collections queue.


**approved.** Conditions:

| Condition |
|---|
| None |

## The integration contract

| Line | What this model does |
|---|---|
| trained | On month ends September 2023 to June 2025, whose three month outcomes had all closed before the test months began. |
| timed | Every feature comes from the month end or earlier; a leakage test recomputes the run length, earlier episodes and last payment for 200 sampled loan months. |
| calibrated | Reliability on the test months is published; the queue multiplies the balance by one minus the probability, so calibration matters. |
| useful | Beats the base rate, the bucket rule collectors use today, and the other candidate on months it never saw. |
| fair | No demographic enters; the features describe the loan and its payments. Cure rates by bucket are published beside the model's. |
| gated | Every gate in this report, including the margin over the bucket rule. |
| served | Scored monthly in the pipeline; the queue is published with the collections page. |
| integrated | Orders the collections queue by balance at risk times the probability of not curing. |
| monitored | Monthly: realised cure rate by queue decile, score PSI, and the rule's AUROC beside the model's. |
| documented | This validation report and the collections page. |
| bounded | Orders calls. Never changes terms, never charges off a loan, and never goes to a borrower as a score. |
| validated | This report, rendered from the manifest before the queue uses the order. |
| explainable | Each queued loan shows the two features that lowered its chance of curing most, in plain words. |
