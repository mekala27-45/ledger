# Validation report: Application fraud on the BAF suite

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `fraud_account` |
| Purpose | Score a bank account application for fraud when it is submitted, so that the riskiest ask for documents before the account opens |
| Tier | 1: Informs a decision a person makes, with a method whose behaviour is hard to inspect |
| Role | sole |
| Status | in use |
| Owner | Head of analytics |
| Prediction time | When the application is submitted; the suite's features describe the application and the activity before it |
| Outcome | The application was fraudulent, as the suite labels it |
| Last validated | 2026-08-31 |
| Conclusion | **approved with conditions** |

## Purpose and scope

Score a bank account application for fraud when it is submitted, so that the riskiest
applications ask for documents before the account opens. The model informs a check a
person completes; it never declines an application. It is tier one because a gradient
boosted model's behaviour is hard to inspect, and because its errors fall unevenly by age.

In scope: the Bank Account Fraud suite (Jesus et al., NeurIPS 2022), a set of synthetic
account applications generated from a real fraud dataset and published with the
protected attributes kept so fairness can be measured. This report reproduces the
suite's evaluation protocol on two of its variants. Out of scope: card fraud, which is
`fraud_card`, and any decision to refuse an account.


## Conceptual soundness

Application fraud is rare and the features are a mix of counts, durations, flags and
categories with missing values marked by negative numbers, which gradient boosted trees
handle without imputation. The suite's own measures are used as the suite defines them:
recall at a 5% false positive rate, and predictive equality, the
lower of the two age groups' false positive rates over the higher at that threshold,
with the groups split at 50. Parity is one.

Age is measured and never used. `customer_age` is a protected attribute on the proxy
list, as is `name_email_similarity`, which is computed from the applicant's name, and
the feature list is checked against that list before training.


## Data and assumptions

A 300,000 application sample of the suite's base variant, and a sample of
the same size of variant II beside it. The suite trains on months 0 to 5
and tests on months 6 and 7. Here the model trains on months 0 to 4,
month 5 chooses the tree count and the threshold a bank could deploy,
and the test is the suite's, so every figure below comes from months the model and its
threshold never saw. The trade is one month of training data, recorded in `DECISIONS.md`.

The suite computes its features at application time and ships no raw history, so there
is nothing to recompute a feature from. The leakage check is a screen instead: a feature
known only after the outcome would predict it almost alone, and the strongest single
feature here, `housing_status`, reaches a test AUROC of 0.724.


## Development evidence

Development AUROC 0.950, validation 0.882,
early stopped at 143 trees.


## Outcomes analysis on held out data

On the test months the model reaches an AUROC of 0.880. At the suite's
threshold it finds 49.0% of fraudulent applications. Applicants aged
50 and over who are not fraudsters are flagged at 9.19%,
against 4.19% for the rest, 2.2 times as often: a
predictive equality of 0.46.

With the threshold fixed on month 5 instead, as a bank would have to
fix it, the test months give a recall of 53.8% at a false positive
rate of 5.94% and a predictive equality of 0.47.

The two variants side by side. Variant II's age groups are about the same size
(50.5% of its applicants are 50 or over, against
18.3% in the base), and its older applicants' fraud rate is
4.7 times the younger group's, against 2.9
times in the base:

| Measure | Base | Variant II |
|---|---|---|
| Applications in the sample | 300,000 | 300,000 |
| Share aged fifty and over | 18.3% | 50.5% |
| Fraud rate, aged fifty and over | 2.34% | 1.82% |
| Fraud rate, under fifty | 0.81% | 0.38% |
| Test AUROC | 0.880 | 0.882 |
| Recall at a five percent false positive rate (the suite's measure) | 49.0% | 49.3% |
| False positive rate, aged fifty and over | 9.19% | 6.96% |
| False positive rate, under fifty | 4.19% | 3.04% |
| Predictive equality (lower rate over higher) | 0.46 | 0.44 |
| Logistic benchmark: recall at the same rate | 47.2% | 47.7% |
| Threshold fixed on month five: recall on the test months | 53.8% | 52.9% |
| Threshold fixed on month five: false positive rate on the test months | 5.94% | 6.07% |
| Threshold fixed on month five: predictive equality | 0.47 | 0.44 |
| AUROC of the features at predicting age fifty and over | 0.782 | 0.788 |

Source: real:baf, Bank account applications in the BAF suite's base variant, a 300,000 sample; variant II beside it, as of 2026-08-31.

By age band, at the suite's threshold on the base variant:

| Group | N | Event rate | Mean score | Calibration gap | Auroc | Flag rate | Fpr | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| under 30 | 15,411 | 0.66% | 0.55% | -0.1% | 0.883 | 2.42% | 2.19% | 36.6% |
| 30 to 39 | 18,963 | 1.19% | 0.82% | -0.4% | 0.858 | 4.38% | 3.91% | 43.8% |
| 40 to 49 | 16,755 | 1.42% | 1.13% | -0.3% | 0.874 | 6.97% | 6.36% | 49.2% |
| 50 to 59 | 7,622 | 2.45% | 1.56% | -0.9% | 0.876 | 10.43% | 9.21% | 58.8% |
| 60 and over | 2,434 | 4.15% | 1.66% | -2.5% | 0.860 | 11.01% | 9.13% | 54.5% |

Source: real:baf, Bank account applications in the BAF suite's base variant, a 300,000 sample; variant II beside it, as of 2026-08-31.


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 6,119 | 0.06% | 0.02% |
| 2 | 6,119 | 0.09% | 0.10% |
| 3 | 6,119 | 0.13% | 0.15% |
| 4 | 6,119 | 0.17% | 0.21% |
| 5 | 6,119 | 0.22% | 0.33% |
| 6 | 6,118 | 0.30% | 0.44% |
| 7 | 6,118 | 0.41% | 0.47% |
| 8 | 6,118 | 0.63% | 1.03% |
| 9 | 6,118 | 1.18% | 2.16% |
| 10 | 6,118 | 6.44% | 9.04% |

Source: real:baf, Bank account applications in the BAF suite's base variant, a 300,000 sample; variant II beside it, as of 2026-08-31.

## Benchmarking

Against the base rate and a logistic regression on the same features, with a flag for
each missing marker and the categories one hot encoded. At the suite's measure the
logistic model's recall is 47.2%.


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.880 | 0.760 | 0.0126 | 0.0044 |
| Base rate | 0.500 | 0.000 | 0.0138 | 0.0042 |
| Logistic on the same features | 0.875 | 0.750 | 0.0129 | 0.0069 |

Source: real:baf, Bank account applications in the BAF suite's base variant, a 300,000 sample; variant II beside it, as of 2026-08-31.

## Limitations

The age gap does not close by leaving age out. The model's features predict whether an
applicant is 50 or over with an AUROC of 0.782; the
strongest carriers after the date of birth count left the feature list are
employment_status, housing_status, current_address_months_count. Removing them one at a time is the search for a less
discriminatory alternative:

| variant | removed | auroc | recall | fpr_older | fpr_younger | ratio |
|---|---|---:|---:|---:|---:|---:|
| Base | Nothing (the model) | 0.880 | 49.0% | 9.19% | 4.19% | 0.46 |
| Base | employment_status | 0.877 | 48.3% | 8.93% | 4.24% | 0.48 |
| Base | employment_status, housing_status | 0.859 | 44.8% | 7.89% | 4.44% | 0.56 |
| Base | employment_status, housing_status, current_address_months_count | 0.854 | 44.2% | 7.80% | 4.46% | 0.57 |
| Variant II | Nothing (the model) | 0.882 | 49.3% | 6.96% | 3.04% | 0.44 |
| Variant II | employment_status | 0.879 | 49.5% | 6.71% | 3.29% | 0.49 |
| Variant II | employment_status, housing_status | 0.860 | 44.3% | 6.62% | 3.38% | 0.51 |
| Variant II | employment_status, housing_status, current_address_months_count | 0.855 | 43.4% | 6.45% | 3.55% | 0.55 |

Source: real:baf, Bank account applications in the BAF suite's base variant, a 300,000 sample; variant II beside it, as of 2026-08-31.

Parity is bought with recall: removing all three moves the base variant's predictive
equality to 0.57 at a recall of 44.2%. The
model is kept, and bounded to asking for documents, because a false flag then costs an
applicant a delay, not an account. The choice is recorded in `DECISIONS.md` and the
search is rerun at every revalidation.

- The suite is synthetic. Its features are generated to match a real dataset's joint
  distribution, not produced by a real application flow, so a real bank's separability
  and drift will differ.
- The suite's labels are final; a real application fraud label arrives weeks later, when
  the account is used.


## Ongoing monitoring plan

Monthly, once labels arrive:


| Measure | Trigger | Action |
|---|---|---|
| False positive rate at the threshold, monthly, by age group | overall above 7.5% or the ratio below its validated value | Reset the threshold on the latest labelled month |
| Recall on labelled applications, monthly | below the validated recall for two months | Revalidate |
| Score PSI, monthly against month five | above 0.25 | Revalidate |

## Effective challenge

From `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-27 | customer_age is on the proxy list and never a feature, yet at the suite's threshold older applicants who are not fraudsters are flagged far more often than younger ones. If the model cannot see age, where does the gap come from? | From the other features. A model trained to predict fifty and over from the fraud model's own features separates the two groups well, and the strongest single carrier was date_of_birth_distinct_emails_4w: a count taken by grouping applications on the applicant's date of birth, so its value depends on how common the applicant's birth year is among applicants. Employment status, housing status and time at the current address come next, and each is also a legitimate fraud signal. | The date of birth count is on the proxy list now, with its reason, so no model may use it. The report publishes a search for a less discriminatory alternative: the next strongest age carriers removed one at a time, with the recall each step costs and the parity it buys, on both variants. The model's use is bounded to asking for documents before an account opens, never to declining one, because a false flag then costs an applicant a delay rather than an account. |
| 2026-09-27 | Recall at a five percent false positive rate sets the threshold on the same months it reports. A bank has to fix its threshold before the applications arrive, and the false positive rate it then gets is whatever the new months give it. | The suite's measure is right for comparing models with each other and with the published results, and wrong as a statement of what the bank would see. | The report and the page publish both: the suite's measure, and the recall, false positive rate and predictive equality on months 6 and 7 at the threshold fixed on month 5. The recall gate uses the fixed threshold, and a gate watches how far the realised false positive rate drifts from its target. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Test AUROC at or above the floor | at least 0.8 | 0.8801 | pass |
| Test recall at the threshold fixed on month five | at least 0.4 | 0.5381 | pass |
| Recall at a five percent false positive rate above the logistic benchmark | at least 0 | 0.0176 | pass |
| Test false positive rate at the threshold fixed on month five | at most 0.075 | 0.0594 | pass |
| Strongest single feature's test AUROC (a feature known after the outcome would stand alone) | at most 0.8 | 0.7235 | pass |
| Predictive equality between the age groups at the suite's threshold | at least 0.8 | 0.4558 | FAIL |
| Expected calibration error on test | at most 0.01 | 0.0044 | pass |

## Validation conclusion

The model does the job its purpose states and passes every critical gate on months it
never saw, at a threshold fixed before them. It does not reach predictive equality
between the age groups on either variant, which is why it is approved with that
condition, bounded to routing applications to document checks, and published with the
alternatives that would trade recall for parity.


**approved with conditions.** Conditions:

| Condition |
|---|
| Remediate before the next validation: Predictive equality between the age groups at the suite's threshold (measured 0.4558) |

## The integration contract

| Line | What this model does |
|---|---|
| trained | On months 0 to 4 of the base variant; month 5 chooses the tree count and the deployable threshold. |
| timed | The suite computes its features at application time and ships no raw history to recompute them from, so the split is temporal and a single feature screen looks for anything known only after the outcome. |
| calibrated | Reliability on the test months is published; the threshold is set by false positive rate, so the score is used as a rank. |
| useful | Beats the base rate and a logistic model on the same features at the suite's own measure, recall at a five percent false positive rate. |
| fair | Predictive equality between applicants aged fifty and over and the rest, on both variants, with a search for a less discriminatory alternative published beside it. |
| gated | Every gate in this report, including the recall at a threshold fixed before the test months. |
| served | Scored in the pipeline; not served by the API, because no live application stream exists here. |
| integrated | An application at or above the threshold asks for documents before the account opens. The model never declines one. |
| monitored | Monthly false positive rate against the threshold, by age group; recall on labelled applications; score PSI. |
| documented | This validation report and the desk page's fairness audit. |
| bounded | Routes applications to document checks only; never declines, never prices, and never sees age. |
| validated | This report, rendered from the manifest before the threshold is used. |
| explainable | A routed application shows the features that moved its score most, in the suite's own terms. |
