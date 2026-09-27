# Validation report: Deposit customer attrition, twelve month horizon

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `attrition` |
| Purpose | Rank customers by the balance the bank stands to lose if they leave in the next twelve months, so retention calls go where they are worth most |
| Tier | 2: Informs a decision a person makes; moderate materiality |
| Role | sole |
| Status | in use |
| Owner | Head of analytics |
| Prediction time | Each month end; features use only that month and earlier |
| Outcome | The customer's primary checking account closes within the next twelve months |
| Last validated | 2026-08-31 |
| Conclusion | **approved** |

## Purpose and scope

Rank the bank's checking customers by the deposits it stands to lose if they leave in the
next twelve months, so that retention calls go where they protect the most balance. The
model informs whom a person calls; it never changes a price, a fee or an account, so it
is tier two.

Out of scope: pricing a retention offer, and any customer who holds only a loan or a card.


## Conceptual soundness

Attrition is a rare outcome driven by a few things a bank can see: a falling balance,
fees, a new relationship, how the customer banks, a complaint, and a savings rate well
below the market. Two candidates were fitted on the same features: a gradient boosted
classifier, for the interactions a real bank's data would have, and a logistic
regression. The champion was chosen on validation month ends for customers neither fit
had seen, and the boosted model had to beat the logistic by 0.005 of
AUROC to earn its complexity. It did not (0.598 against
0.597), so the model is the logistic regression.

The retention list multiplies the probability by the customer's balances, so the
probability is used as a probability, and calibration is part of the model's job.


## Data and assumptions

One row per customer with an open checking account per month end. The outcome is known
only twelve months later, and the split is built around that: training on
month ends September 2023 to February 2024, validation on month ends March to May 2024, test on
month ends June to August 2025 (109,061 customer months,
7,060 of them followed by a closure). Every training and validation
outcome was known before the first test month end, which is why the windows are apart.
The same customers appear in every month, so early stopping and the choice of champion
use customers held out of the fit (80% of customers fit).

A leakage test recomputed the month's fees, activity, payroll deposits and inflow for
200 sampled customer months from the posted entries and matched
every one. Age is never a feature; it is used only for the audit below.


## Development evidence

Development AUROC 0.596, validation 0.596.
What moves the score most (standardised coefficients for a logistic regression, share of
gain for a boosted model):

| feature | weight |
|---|---:|
| uses digital banking | -0.18 |
| has complained | 0.17 |
| customer for under a year | 0.14 |
| money going out | -0.05 |
| time as a customer | -0.05 |
| savings rate far below market | 0.04 |
| holds savings or a CD | 0.04 |
| savings and time balances | 0.04 |
| money coming in | 0.02 |
| checking balance | 0.02 |
| less than three months of history | 0.01 |
| checking balance fell sharply last month | 0.01 |
| overdraft last month | -0.01 |
| payroll deposits | 0.01 |
| checking balance change over three months | -0.01 |
| income | 0.00 |
| account activity | 0.00 |
| fees charged last month | 0.00 |


## Outcomes analysis on held out data

On the test months the model reaches an AUROC of 0.583, and the
LightGBM 0.579. That looks weak until it is set against the
ceiling: the generator's own monthly hazards, used as a score with perfect knowledge of
the months ahead, reach 0.588. Most attrition in this bank is chance, as it
is in most banks, and the model reaches 94% of the separation there is
to find.

The top 10% of scores holds 17.4% of the customers who
went on to close. Ranked by probability, it holds 11.2% of the
balances that left; ranked by expected balance at risk, as the list is, it holds
47.1% of the balances and 11.1%
of the closers: fewer people, more money.

By age band at the top tenth threshold:

| Group | N | Event rate | Mean score | Calibration gap | Auroc | Flag rate | Fpr | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| under 25 | 14,988 | 6.46% | 7.04% | +0.6% | 0.573 | 8.82% | 8.27% | 16.8% |
| 25 to 34 | 18,460 | 6.10% | 7.11% | +1.0% | 0.605 | 9.15% | 8.62% | 17.4% |
| 35 to 49 | 37,400 | 6.46% | 7.52% | +1.1% | 0.577 | 10.22% | 9.84% | 15.7% |
| 50 to 64 | 27,666 | 6.74% | 7.66% | +0.9% | 0.579 | 10.31% | 9.72% | 18.4% |
| 65 and over | 10,547 | 6.51% | 8.30% | +1.8% | 0.594 | 11.59% | 10.85% | 22.1% |

Source: generated, Harborline customers with an open checking account at a month end, September 2023 to August 2026, seed 20260831, as of 2026-08-31.


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 10,907 | 4.81% | 4.69% |
| 2 | 10,906 | 5.21% | 5.14% |
| 3 | 10,906 | 5.54% | 4.71% |
| 4 | 10,906 | 5.82% | 5.19% |
| 5 | 10,906 | 6.16% | 5.20% |
| 6 | 10,906 | 6.77% | 6.64% |
| 7 | 10,906 | 7.60% | 6.59% |
| 8 | 10,906 | 8.30% | 7.07% |
| 9 | 10,906 | 9.66% | 8.21% |
| 10 | 10,906 | 15.12% | 11.29% |

Source: generated, Harborline customers with an open checking account at a month end, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Benchmarking

Against the base rate and the candidate that was not chosen, on the test months:


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.583 | 0.166 | 0.0603 | 0.0103 |
| Base rate | 0.500 | 0.000 | 0.0606 | 0.0100 |
| LightGBM on the same features | 0.579 | 0.158 | 0.0602 | 0.0126 |

Source: generated, Harborline customers with an open checking account at a month end, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Limitations

- The generator's customers leave for the reasons it was written with. Real attrition
  has causes no bank sees, such as a move or a competitor's offer.
- Closure of the primary checking account is the outcome. A customer who keeps the
  account open and moves their salary elsewhere has left in every way that matters, and
  this label does not see it.
- A retention call changes the outcome it predicts. Once the list is used, the model's
  measured capture is no longer a clean measure of the model.


## Ongoing monitoring plan

Monthly:


| Measure | Trigger | Action |
|---|---|---|
| Score PSI, monthly against validation | above 0.25 | Revalidate |
| Share of the list's customers who close within twelve months | below the test capture for two quarters | Refit |
| Flag rate by age band | any band below half the highest | Review the features |

## Effective challenge

From `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-27 | The first split trained on every month end up to December 2024 and tested on the summer of 2025. A December 2024 label says whether the customer left by December 2025, which the bank could not have known when it scored the summer of 2025. | A random or plain temporal split lets training labels come from the future of the test months whenever the outcome window is longer than the gap. The model a bank could actually have fitted on 31 May 2025 only had month ends whose windows had closed by then. | Training uses month ends September 2023 to February 2024, validation March to May 2024, and test June to August 2025, so every training and validation outcome was known before the first test month end. The gap is stated in the report beside the split. |
| 2026-09-27 | Sorted by probability alone, the top of the retention list fills with new customers holding a few hundred dollars. A retention call costs the same whoever answers. | The list exists to protect deposits. What the bank stands to lose is the probability times the balances the customer holds, and the two orderings put different people at the top. | The list is ranked by expected balance at risk. The report publishes, for the top tenth of the test months, the share of closers and the share of their balances found by each ordering, so the trade between the two is visible. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Share of the achievable separation reached: (AUROC minus one half) over (the ceiling minus one half) | at least 0.5 | 0.9417 | pass |
| Test AUROC against the other candidate's (the choice on validation must not cost more than a hundredth) | at least -0.01 | 0.0040 | pass |
| Test average precision above the base rate | at least 0 | 0.0304 | pass |
| Share of closers in the top tenth of scores, test months (a tenth is no better than chance) | at least 0.15 | 0.1744 | pass |
| Point in time recompute of sampled customer months | at least 200 | 200.0000 | pass |
| Expected calibration error on test | at most 0.02 | 0.0103 | pass |

## Validation conclusion

The model orders customers the way its purpose asks, reaches most of the separation the
data holds on month ends it never saw, and its probability is calibrated well enough to
multiply a balance. It is approved for ordering the retention list, with the ceiling
restated at every revalidation, because a real bank has no generator to measure it by.


**approved.** Conditions:

| Condition |
|---|
| None |

## The integration contract

| Line | What this model does |
|---|---|
| trained | On month ends September 2023 to February 2024, whose twelve month outcomes had all closed before the test months began. |
| timed | Every feature comes from the month end or earlier; a leakage test recomputes the month's activity for 200 sampled customer months from posted entries. |
| calibrated | Reliability on the test months is published, and the probability is used as a probability: it multiplies the balance. |
| useful | Beats the base rate, matches or beats the other candidate on months it never saw, and reaches a stated share of the separation the generator's own hazards reach. |
| fair | Flag rate and capture by age band at the top tenth. Age never enters the model. |
| gated | Every gate in this report. |
| served | Scored monthly in the pipeline; the retention list is published with the deposits page. |
| integrated | Orders the retention list by expected balance at risk: probability times the balances held. |
| monitored | Monthly score PSI; capture of the list against closures as they happen; closure rate by age band. |
| documented | This validation report and the deposits page. |
| bounded | Chooses whom to call. Never changes a price, a fee or an account, and never goes to a customer as a score. |
| validated | This report, rendered from the manifest before the list is used. |
| explainable | Each customer on the list shows the two features that raised the probability most, in plain words. |
