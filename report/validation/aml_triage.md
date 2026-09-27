# Validation report: Alert triage for transaction monitoring

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `aml_triage` |
| Purpose | Rank the transaction monitoring rules' alerts so an investigator opens the likeliest real typology first |
| Tier | 2: Informs a decision a person makes; moderate materiality |
| Role | sole |
| Status | in use |
| Owner | Head of analytics |
| Prediction time | When the alert fires; history features use only the account's entries before the alert window opened |
| Outcome | The alert overlaps an injected typology episode of the same kind on the same account |
| Last validated | 2026-08-31 |
| Conclusion | **approved** |

## Purpose and scope

The transaction monitoring rules fire alerts; investigators work them in the order the
queue presents them. This model sets that order: the alert most likely to be a real
typology comes first. It informs which alert a person opens, never whether an alert is
closed or reported, so it is tier two.

Out of scope: deciding a disposition, filing a suspicious activity report, and any alert
source other than the four rules in `rules/aml_typologies.yaml`.


## Conceptual soundness

Triage is a ranking problem over a small, imbalanced set, so the method is a logistic
regression on standardised features whose coefficients an investigator can read: the
alert's own size, entry count, counterparties and branches, which rule fired, the
account's age, its cash deposits and inflow in the ninety days before the alert window
opened, and how many alerts it had before. The benchmarks are the base rate and the
order the rules alone imply, each rule ranked by its precision on the development months.


## Data and assumptions

Every alert the rules fired on Harborline Bank's deposit accounts:
649 alerts, 429 of them overlapping an injected
typology episode of the same kind on the same account. The label is the generator's truth,
which a real program would not have; its labels would be investigator dispositions.

Split by when the alert closed: development September 2023 to August 2025
(445 alerts), validation September 2025 to February 2026
(98), test March to August 2026
(106, 59 true).

A leakage test recomputed the history features of 200 sampled alerts
from raw ledger entries strictly before each alert window and matched every one. No
demographic attribute or proxy is a feature.


## Development evidence

Development AUROC 0.999, validation 1.000.
The coefficients, standardised, largest first:

| feature | coefficient |
|---|---:|
| prior_cash_90d | -3.32 |
| branches | 1.86 |
| rule_structuring | -1.56 |
| prior_alerts | 0.94 |
| rule_round_tripping | 0.82 |
| rule_rapid_movement | 0.81 |
| counterparties | 0.60 |
| rule_mule | 0.57 |
| log_amount | 0.55 |
| entries | 0.40 |
| log_tenure_days | -0.23 |
| log_prior_inflow_90d | 0.16 |
| amount_vs_monthly_inflow | 0.03 |


## Outcomes analysis on held out data

On the test months the model reaches an AUROC of 1.000 and an average
precision of 1.000. Within the 72
structuring alerts, 25 of them true, where the rules alone
cannot order anything, its AUROC is 1.000.

These are properties of the generator, not of the method: its legitimate lookalikes and its
injected typologies do not overlap. Without the cash history and branch count the AUROC is
0.997; the rules' own order reaches 0.788.


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 11 | 0.04% | 0.00% |
| 2 | 11 | 0.27% | 0.00% |
| 3 | 11 | 0.91% | 0.00% |
| 4 | 11 | 3.67% | 0.00% |
| 5 | 11 | 81.86% | 72.73% |
| 6 | 11 | 99.39% | 100.00% |
| 7 | 10 | 99.83% | 100.00% |
| 8 | 10 | 99.92% | 100.00% |
| 9 | 10 | 99.96% | 100.00% |
| 10 | 10 | 99.99% | 100.00% |

Source: generated, Every alert the four rules fired on Harborline deposit accounts, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Benchmarking

Against the base rate, the rules' own order, and this model with its two strongest features
removed, on the test months:


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 1.000 | 1.000 | 0.0071 | 0.0155 |
| Base rate | 0.500 | 0.000 | 0.2601 | 0.1489 |
| The rules' own order | 0.788 | 0.576 | 0.1576 | 0.1276 |
| This model without cash history and branches | 0.997 | 0.994 | 0.0362 | 0.0751 |

Source: generated, Every alert the four rules fired on Harborline deposit accounts, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Limitations

- The labels are injected truth. An investigator's disposition is noisier, arrives weeks
  later and is shaped by the queue order itself, which this data cannot show.
- The legitimate lookalikes are written to look like the typologies on the rule's terms,
  not on every feature, so the model's separation here overstates what it would do on a
  real portfolio.
- Four rules, four typologies. Anything the rules do not fire on never reaches the queue.


## Ongoing monitoring plan

Monthly, against the queue as investigators work it:


| Measure | Trigger | Action |
|---|---|---|
| Precision of the queue's first quarter against investigator dispositions | below the rules' own order for two months | Refit on dispositions |
| Score PSI, monthly against development | above 0.25 | Revalidate |
| Alert mix by rule | any rule's share moves by half | Review the rule thresholds before the model |

## Effective challenge

From `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-27 | On months it never saw, the triage model put every alert that matched an injected typology ahead of every legitimate lookalike: an AUROC of one. | The generator writes its lookalikes and its criminals from separate recipes. A cash intensive business deposits cash every week at one branch; a structurer is new to cash and spreads deposits across several branches. Removing the cash history and the branch count still leaves the alert size, its entry count and the account's earlier alerts, and the separation survives, so it is not one leaked column. It is two synthetic populations that do not overlap. A real program's labels are investigator dispositions, which are noisier and arrive late. | The report publishes the ranking without the two strongest features and the rules' own order as benchmarks, states that the measured quality is a property of the generator, and makes investigator dispositions the monitoring measure the model would be refit on before any real use. |
| 2026-09-27 | The mule, rapid movement and round tripping rules fired no false alerts on this data, so a model that only learned which rule fired would already rank most of the queue correctly. | Pooled over all four rules, AUROC mostly rewards putting those three rules' alerts first, which each rule's own precision on the development months already does. The only alerts where order is a real question are structuring alerts, where the rule's precision is under half. | A gate now measures the model within structuring alerts alone, where the rules' order carries no information, and the benchmark table includes ranking by each rule's development precision. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Test AUROC at or above the floor | at least 0.8 | 1.0000 | pass |
| Test average precision above the rules' own order | at least 0 | 0.1879 | pass |
| Test AUROC within structuring alerts, where the rules' order says nothing | at least 0.8 | 1.0000 | pass |
| Point in time recompute of sampled alerts | at least 200 | 200.0000 | pass |
| Expected calibration error on test | at most 0.1 | 0.0155 | pass |
| Test AUROC without the cash history and branch count features | at least 0.75 | 0.9968 | pass |

## Validation conclusion

The model orders the queue the way its purpose asks and passes every gate on months it
never saw. Its measured quality is a property of the generator, whose lookalikes and
typologies do not overlap, so the approval is for ordering this demonstration's queue;
on a real portfolio it would be refit and re-measured on investigator dispositions first.


**approved.** Conditions:

| Condition |
|---|
| None |

## The integration contract

| Line | What this model does |
|---|---|
| trained | On alerts that closed before September 2025, labelled by the generator's injected truth. |
| timed | History features stop at the alert window's start; a leakage test recomputes 200 sampled alerts from raw entries. |
| calibrated | Reliability on the test months is published; the queue uses the score as a rank. |
| useful | Beats the base rate and the order the rules alone imply, including within structuring alerts, where the rules cannot rank at all. |
| fair | No demographic enters; the features are the alert's facts and the account's own history. |
| gated | Every gate in this report, including an ablation without the two features the generator made most different. |
| served | Scored in the pipeline; the ranked queue is published with the crime page. |
| integrated | Sorts the case queue: an investigator opens alerts in the model's order within each month. |
| monitored | Queue capture against investigator dispositions once they exist; monthly score PSI; alert mix by rule. |
| documented | This validation report and docs/crime.md. |
| bounded | Orders alerts; never closes one, never files anything, and never replaces an investigator's disposition. |
| validated | This report, rendered from the manifest before the queue uses the order. |
| explainable | Each alert shows the rule's statement in plain words and the features that moved its score most. |
