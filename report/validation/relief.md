# Validation report: Monetary relief on consumer complaints

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

| | |
|---|---|
| Model | `relief` |
| Purpose | Route complaints likely to end in a refund to the team that can fix the cause, and rank issues by the relief they are likely to cost |
| Tier | 2: Informs a decision a person makes; moderate materiality |
| Role | sole |
| Status | development |
| Owner | Head of analytics |
| Prediction time | When the complaint is filed; only the narrative and what the consumer chose on the form |
| Outcome | The company closed the complaint with monetary relief |
| Last validated | 2026-08-31 |
| Conclusion | **not approved** |

## Purpose and scope

Route complaints likely to end in monetary relief to the team that can fix the cause,
and rank issues by the relief they are likely to cost. In a bank, a model like this is
for routing and root cause. It must never decide whether a consumer gets relief, and it
must never rank consumers; it ranks complaints and issues. It informs a person, so it is
tier two.

The data are real: complaints with narratives from the Consumer Financial Protection
Bureau's public database, about real companies, exactly as the Bureau publishes them. The
Bureau states that the database is "not a statistical sample of consumers' experiences
in the marketplace".


## Conceptual soundness

Whether a complaint ends in a refund depends on what went wrong and with whom: the
product, the issue, the company, and what the consumer describes. The method is a
logistic regression on TF-IDF of the narrative, one and two word terms, with the form's
product, sub product, issue and company one hot encoded. A transformer would read the
narrative better; it needs model weights this build cannot download, and the always
available path is the one validated here.

The benchmark that matters is a model on the form's metadata alone: if the narrative
adds nothing, reading it is not worth the risk it carries.


## Data and assumptions

46,082 closed complaints with narratives. Training on complaints
received September 2024 to December 2025, validation January to March 2026, test
April to July 2026 (7,905 complaints, 532
ending in monetary relief). The rate of relief rose from 1.4% in the
training months to 6.7% in the test months.

Only fields the consumer writes when filing are features; a check refuses anything the
company writes afterwards. 28 words that name a protected basis are
removed from the vocabulary, leaving 30,000 terms, and the Bureau's
tags for older Americans and servicemembers are used only for the audit below.


## Development evidence

Development AUROC 0.989, validation 0.883.
The terms that move the score most:

| raises_relief | weight_up | lowers_relief | weight_down |
|---|---:|---|---:|
| atm | 1.66 | funds | -0.96 |
| charged | 1.53 | open | -0.80 |
| checking account | 1.33 | payment | -0.71 |
| fee | 1.29 | account year | -0.68 |
| email | 1.23 | showed | -0.68 |
| didn | 1.21 | loan | -0.66 |
| checking | 1.09 | wrong | -0.65 |
| bofa | 1.08 | tried | -0.64 |
| bank | 1.07 | verification | -0.62 |
| claim | 1.04 | believe | -0.60 |
| refunded | 1.02 | issues | -0.59 |
| balance | 1.00 | day | -0.59 |
| card stolen | 0.99 | income | -0.58 |
| offer | 0.98 | points | -0.56 |
| year | 0.98 | deposited | -0.55 |


## Outcomes analysis on held out data

On the test months the model reaches an AUROC of 0.869, against
0.855 for the metadata alone. At the operating point, the top
5% of scores set on the validation months, it flags
405 complaints with a precision of 39.5%,
5.9 times the base rate, and finds 30.1% of the
complaints that ended in relief.

By the Bureau's tags, at the operating point:

| Group | N | Event rate | Mean score | Calibration gap | Auroc | Flag rate | Fpr | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Older American | 477 | 14.88% | 13.23% | -1.7% | 0.820 | 14.47% | 10.10% | 39.4% |
| Older American, servicemember | 119 | 12.61% | 9.69% | -2.9% | 0.790 | 8.40% | 4.81% | 33.3% |
| Other | 6,577 | 6.05% | 6.72% | +0.7% | 0.874 | 4.58% | 2.98% | 29.4% |
| Other, servicemember | 732 | 6.56% | 6.69% | +0.1% | 0.848 | 3.42% | 2.19% | 20.8% |

Source: real:cfpb, Complaints with narratives in the Bureau's public database, a sample from September 2024 to August 2026, as of 2026-08-31.


Calibration on the test sample, ten equal count bins:

| Bin | Accounts | Predicted | Observed |
|---:|---:|---:|---:|
| 1 | 791 | 0.05% | 0.00% |
| 2 | 791 | 0.19% | 0.13% |
| 3 | 791 | 0.33% | 0.13% |
| 4 | 791 | 0.66% | 0.76% |
| 5 | 791 | 1.44% | 0.63% |
| 6 | 790 | 2.97% | 3.04% |
| 7 | 790 | 5.36% | 6.46% |
| 8 | 790 | 9.21% | 9.49% |
| 9 | 790 | 16.18% | 15.95% |
| 10 | 790 | 35.17% | 30.76% |

Source: real:cfpb, Complaints with narratives in the Bureau's public database, a sample from September 2024 to August 2026, as of 2026-08-31.

## Benchmarking

Against the base rate and a logistic regression on the form's metadata alone, on the test months:


| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.869 | 0.738 | 0.0528 | 0.0073 |
| Base rate | 0.500 | 0.000 | 0.0656 | 0.0532 |
| The form's metadata alone | 0.855 | 0.710 | 0.0539 | 0.0128 |

Source: real:cfpb, Complaints with narratives in the Bureau's public database, a sample from September 2024 to August 2026, as of 2026-08-31.

## Limitations

- The complaints are a sample of the Bureau's public database, and the database is not a
  sample of consumers: people who complain, and who write a narrative, are not typical.
- The outcome is the company's own label for its response. Companies differ in what
  they call monetary relief.
- The rate of relief rose across the window, so the probabilities run low on the test
  months; the ranking is what the model is used for.


## Ongoing monitoring plan

Monthly, against complaints as they close:


| Measure | Trigger | Action |
|---|---|---|
| Precision at the operating point against closed complaints | below twice the base rate for a quarter | Refit |
| The monthly base rate of monetary relief | moves by half | Reset the operating point |
| Flag rate by the Bureau's tags | any group below half the highest | Review the vocabulary |

## Effective challenge

From `DECISIONS.md`:


| Date | Challenge | Response | What changed |
|---|---|---|---|
| 2026-09-27 | Complaints received in late 2024 ended in monetary relief about one time in seventy; by mid 2026 it was closer to one in fourteen. A model fitted on the early months will score the later ones too low, and a probability threshold chosen on 2025 would flag almost nothing in 2026. | The ranking survives a shift in the base rate far better than the probabilities do. The operating point is a capacity, not a probability: a review team that can read one complaint in twenty. | The operating point flags the top twentieth of scores, set on the validation months immediately before the test months. Reliability on the test months is published with the drift stated beside it, the calibration gate is non critical, and the monitoring plan resets the operating point when the monthly base rate moves by half. |
| 2026-09-27 | Consumers write about their age, their disability, their military service and their family. A text model can learn that an elderly widow is more likely to get a refund, which is a protected basis entering a routing decision by the back door. The Bureau's own tags mark older Americans and servicemembers. | Routing is not a credit decision, but it decides whose complaint a person reads first, and the same reasoning that keeps age out of a scorecard applies. | `rules/proxies.yaml` now lists words a text model may not learn from, and the relief model drops them, and any phrase containing them, from its vocabulary. The Bureau's tags are never features; they are used only to audit flag rates by group, and a gate watches the ratio. |

## Promotion gates

| Gate | Threshold | Measured | Result |
|---|---|---:|---|
| Test AUROC above the metadata only model: the narrative has to add something | at least 0.02 | 0.0140 | FAIL |
| Test precision at the operating point over the base rate (lift) | at least 2 | 5.8702 | pass |
| Test AUROC at or above the floor | at least 0.7 | 0.8688 | pass |
| Lowest over highest flag rate across the Bureau's tag groups | at least 0.5 | 0.2361 | FAIL |
| Expected calibration error on test | at most 0.02 | 0.0073 | pass |

## Validation conclusion

The model ranks complaints well, but the narrative adds only 0.014 of
AUROC to what the form's metadata already says, short of the two hundredths the gate
asks for. Reading consumers' own words is not worth its risk for that gain, so the model
is not approved and stays in development; the conduct risk view ranks issues with
the model on the form's metadata alone. It would be revisited with a transformer, which reads a
narrative better than a bag of words, once model weights can be reached.


**not approved.** Conditions:

| Condition |
|---|
| Test AUROC above the metadata only model: the narrative has to add something (measured 0.01401) |

## The integration contract

| Line | What this model does |
|---|---|
| trained | On complaints received September 2024 to December 2025; validation January to March 2026 sets the operating point. |
| timed | Only fields the consumer writes when filing; a check refuses any field the company writes afterwards, such as its response. |
| calibrated | Reliability on the test months is published; the base rate rose over the window, which the report states. |
| useful | Beats a model on the form's metadata alone, so the narrative adds something, and lifts precision well above the base rate at the operating point. |
| fair | Words naming a protected basis are removed from the vocabulary; flag rates by the Bureau's older American and servicemember tags are audited. |
| gated | Every gate in this report. |
| served | Scored in the pipeline over the loaded window; not served by the API. |
| integrated | Not integrated. Until the narrative earns its place, the conduct risk view ranks issues with the model on the form's metadata alone. |
| monitored | Monthly: precision at the operating point against closed complaints, the base rate, and flag rates by tag. |
| documented | This validation report and the complaints page. |
| bounded | Routes and ranks. Never decides whether a consumer gets relief, and never ranks consumers. |
| validated | This report, rendered from the manifest before the ranking is used. |
| explainable | The terms that raise and lower the score most are published; a routed complaint shows its product and issue. |
