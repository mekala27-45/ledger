# Harborline Bank: board pack

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

**For the quarter ended 2026Q2, with data to 2026-08-31.**
From the head of analytics to the board.

## The bank at a glance

We closed the period with total assets of $1,033.6M, gross loans of
$720.0M and deposits of $930.6M. Net income over the
last twelve months was $13.4M. Our net interest margin for the quarter
was 5.60%, the efficiency ratio 50.9%, return on assets
1.72% and return on equity 17.8%. Nonperforming loans were
0.49% of gross loans, and the allowance for credit losses stood at
1.90% of loans. Every one of these figures is computed from the
general ledger, which reconciled to the cent this quarter apart from one break I describe
below.

Against 191 real FDIC insured banks of our size in our region, our margin
and returns sit near the top of the range, for one reason: 28% of
our loans are card and consumer installment lending, where most of our peers lend mortgages
and to businesses. That same mix is where our credit risk sits.

| Ratio | Harborline (fictional) | Peer 10th | Peer median | Peer 90th | Share of peers below | Better when |
|---|---:|---:|---:|---:|---:|---|
| Net interest margin | 5.60% | 2.48% | 3.39% | 4.33% | 99% | higher |
| Efficiency ratio | 50.94% | 49.89% | 70.91% | 92.18% | 12% | lower |
| Return on assets | 1.72% | 0.20% | 0.80% | 1.71% | 91% | higher |
| Return on equity | 17.80% | 2.00% | 7.60% | 15.22% | 96% | higher |
| Nonperforming loans | 0.49% | 0.02% | 0.52% | 1.99% | 49% | lower |
| Allowance to loans | 1.90% | 0.50% | 0.93% | 1.47% | 98% | higher |
| Capital ratio (simplified) | 19.35% | 12.58% | 15.38% | 30.39% | 74% | higher |
| Loans to deposits | 78.36% | 69.52% | 89.07% | 107.03% | 20% | higher |

Source: real:fdic, FDIC insured institutions, $0.5 to $2.5 billion in assets, CT DE MA MD NJ NY PA, 2026Q2, as of 2026-08-31.

What moved this quarter, largest first:

| Rank | Insight | Materiality |
|---:|---|---:|
| 1 | Deposits rose $14.1M from 2026Q1 to 2026Q2 (+1.6%). | $14,119,114 |
| 2 | Installment balances rose $8.4M over the last quarter, to $152.1M. | $8,421,146 |
| 3 | Mortgage balances fell $7.1M over the last quarter, to $518.5M. | $7,071,081 |
| 4 | Gross loans rose $2.6M from 2026Q1 to 2026Q2 (+0.4%). | $2,606,214 |
| 5 | Provision expense fell $2.1M from 2026Q1 to 2026Q2 (-41.7%). | $2,076,773 |
| 6 | Net income rose $1.8M from 2026Q1 to 2026Q2 (+72.4%). | $1,832,114 |
| 7 | Net income in 2026-04 was $1.9M against a trailing average of $0.7M, outside two standard deviations. | $1,224,641 |
| 8 | Net income in 2025-05 was -$0.5M against a trailing average of $0.5M, outside two standard deviations. | $1,077,407 |

## Credit quality

The two installment vintages we wrote under the loosened cutoff, 2024Q4 and 2025Q1,
reached 10.4% cumulative default by twelve months on book, against
4.0% for the vintages before them. The recession from 2025-03 to 2025-05 added to it.
Both effects are real in our data and our models recover them, but neither is visible to the
application scorecard, which ranks risk well and understates its level on those vintages.

Delinquency rolls the way it should in a book that mostly pays: a current loan moves to thirty
days past due at 1.46% a month, and
once there, 54.59% roll on to sixty while 42.21% cure.

Expected loss on the open installment book is $8,409,265 on exposure of
$152.1M (5.53%). That uses the scorecard's probability of default
adjusted, vintage by vintage, by how far observed defaults have run above it, and loss given
default of 79.6% from our own recoveries. On the raw scorecard
probability the figure would be $4,925,055.

| Score band | Loans | Exposure | PD (with overlay) | LGD | Expected loss | EL rate |
|---|---:|---:|---:|---:|---:|---:|
| under 560 | 371 | $4.6M | 23.69% | 79.6% | $889,783 | 19.40% |
| 560 to 599 | 7,032 | $71.2M | 9.82% | 79.6% | $5,787,865 | 8.13% |
| 600 to 639 | 6,701 | $62.4M | 3.16% | 79.6% | $1,625,988 | 2.61% |
| 640 and over | 1,724 | $14.0M | 0.91% | 79.6% | $105,629 | 0.75% |

Source: generated, Harborline installment loans, seed 20260831, as of 2026-08-31.

A simplified lifetime view in the shape of CECL, using our vintage curves and the Federal
Reserve's supervisory baseline for unemployment, puts lifetime losses on the open book at
$19,055,866. It is an illustration of the method, not an audited estimate.

Our portfolio limits all held:

| Limit | Measured | Limit value | Status |
|---|---:|---:|---|
| Loosened vintages' share of installment balances | 13.03% | 35.00% | within |
| Installment balances 30 or more days past due | 2.58% | 4.00% | within |
| Nonperforming loans to gross loans | 0.54% | 1.00% | within |
| Mortgages' share of gross loans | 72.02% | 75.00% | within |

## Fraud and the desk

The card fraud model decides at the threshold that minimises what fraud costs us, not at the
one that maximises accuracy. On the three test months it would have cost
$24,927 in declined good transactions and missed fraud, against
$1,573,327 if we approved everything and
$89,153 at the threshold accuracy would pick. It declines with
precision 74.8% and catches 97.6%
of fraud. The analyst queue takes only alerts at the stricter queue point, where precision is
89.7%.

I would ask the board to read our fraud figures the way the desk does. A fraud label arrives only
when the chargeback window closes, 60 days after the
transaction. At the end of August, 66.1% of the summer's
decisions were still unlabelled, and precision over the labelled ones was
73.4%. A report that counted the unlabelled
declines as mistakes would have shown 27.0%. We never
publish that number.

## Financial crime

Our four monitoring rules fired 649 alerts over the three years, about
18.0 a month, and found 362 of the
422 complete laundering episodes planted in our data to test them. Structuring
is where our investigators' time goes: legitimate cash businesses deposit just under the
reporting threshold, and only 41.5% of structuring alerts are
real. The queue is ordered by a triage model so the likeliest cases are opened first; it never
closes an alert on its own. No suspicious activity report is filed from this data.

| Rule | Alerts | Precision | Complete episodes | Found | Recall | Posted in part | Alerts per 100k entries |
|---|---:|---:|---:|---:|---:|---:|---:|
| Structuring | 376 | 41.5% | 204 | 156 | 76.5% | 0 | 4.57 |
| Rapid movement | 100 | 100.0% | 100 | 100 | 100.0% | 0 | 1.22 |
| Round tripping | 90 | 100.0% | 24 | 24 | 100.0% | 19 | 1.09 |
| Mule fan in | 83 | 100.0% | 94 | 82 | 87.2% | 0 | 1.01 |

Source: generated, Harborline deposit accounts and their entries, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Fair lending

Our mortgage applications are generated data with no real HMDA filing behind them, so the team
runs our fair lending method on New Jersey's public register, the data an examiner would start
from. Across 215,881 decided mortgage applications in 2024 and 2025,
Black applicants were denied at 24.0% against 10.7% for
white non Hispanic applicants. With income, loan size, loan to value, debt to income, the
product, the underwriting system and the lender held fixed, the odds ratio is
1.76 (1.67 to 1.85). The public
file has no credit scores, so this is not a finding about any lender; it is the gap a lender's
own file review would have to explain, and the one I would expect an examiner to ask us about
first.

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

Our own scorecard uses none of the 32 protected attributes and proxies
on our list, every model's features are tested against that list, and every decline carries its
principal reasons.

## Model risk

We use 7 models in this pack. Each has an SR 11-7 style validation report,
a tier, an owner and a monitoring plan; 15 challenges were raised and
answered during development and each is on record.

| Model | Title | Function | Tier | Role | Status | Last validated | Conclusion | Test AUROC |
|---|---|---|---|---|---|---|---|---:|
| pd_scorecard | Probability of default scorecard (champion) | f02 | 1 | champion | in use | 2026-08-31 | approved with conditions | 0.662 |
| pd_challenger | Probability of default challenger (monotone GBM) | f02 | 1 | challenger | validated | 2026-08-31 | not approved | 0.667 |
| fraud_card | Card transaction fraud (the desk's model) | f04 | 1 | sole | in use | 2026-08-31 | approved | 1.000 |
| fraud_account | Application fraud on the BAF suite | f04 | 1 | sole | in use | 2026-08-31 | approved with conditions | 0.880 |
| aml_triage | Alert triage for transaction monitoring | f05 | 2 | sole | in use | 2026-08-31 | approved | 1.000 |
| attrition | Deposit customer attrition, twelve month horizon | f06 | 2 | sole | in use | 2026-08-31 | approved | 0.583 |
| cure | Cure within ninety days for delinquent loans | f09 | 2 | sole | in use | 2026-08-31 | approved | 0.787 |

The probability of default scorecard is approved with a condition: its calibration on the
loosened and recession vintages, which the expected loss overlay covers until it is
recalibrated. The challenger model ranks marginally better but not by enough to give up the
scorecard's directly stated reasons for a decline, and stays in shadow.

## Controls

Of 792 ledger account months, 786 tie to
the cent between the balance our ledger reports and the sum of its postings. The one break is
in savings deposits, account 2010: $4,217.36 first
appearing in 2026-03 and carried into every month since. It was planted to prove
the control finds it, and it did, to the account and the month. Every control account ties to
its sub ledger in all 216 checks. Each of the
3 defect types planted in the source data was caught at exactly the
count planted.

## The one recommendation

**Hold the installment cutoff at 580, and hold reserves on the
installment book at the overlay adjusted expected loss of $8,409,265, which is
$3,484,210 above what the scorecard's own probability implies.**

The cutoff is in the right place. On every loan whose first year we have seen, lowering it to
560 would have lost $196,493 net, and raising it to
600 would have given up $1,641,356 more margin than it saved in
losses. The risk is in the level of default on the vintages we have already written, not in
whom we approve today, so the answer is reserves, not a tighter policy.

This lands on consumer lending, and on the scorecard's recalibration condition in model risk
management.

What would change it: if the observed over expected ratio on the vintages written since the
recession falls back toward one, the overlay and the reserve build shrink with it. If a new
loosening shows up in the vintage curves, the cutoff question reopens and I will bring it back.

| Cutoff | Loans declined (+) or added (-) | Defaults among them | Losses avoided | Margin forgone | Net benefit |
|---:|---:|---:|---:|---:|---:|
| 560 | -2,333 | -287 | -$3,096,989 | -$2,900,496 | -$196,493 |
| 580 | 0 | 0 | $0 | $0 | $0 |
| 600 | 3,806 | 259 | $2,669,791 | $4,311,147 | -$1,641,356 |
| 620 | 7,038 | 414 | $4,249,056 | $7,587,812 | -$3,338,757 |
| 640 | 9,085 | 461 | $4,691,778 | $9,450,846 | -$4,759,067 |

Source: generated, booked installment loans with an observed twelve month outcome, seed 20260831, as of 2026-08-31.

## Appendix: exhibits

Every figure in this pack comes from a query the pipeline ran for this edition. Each exhibit,
with where its data lives:

| Exhibit | Data | Source |
|---|---|---|
| Harborline against real peers | `results/f01/peer_strips.parquet` | real:fdic, FDIC BankFind financials |
| The ratios every bank reports, monthly | `results/f01/ratios_monthly.parquet` | generated, metrics/bank.yaml |
| Monthly transitions between delinquency buckets | `results/f02/roll_rates.parquet` | generated, warehouse marts |
| Share of loans not yet defaulted, by score band at application | `results/f02/survival_curves.parquet` | generated, lifelines |
| Cumulative default rate by months on book, one line per origination quarter | `results/f02/vintages.parquet` | generated, warehouse marts |
| Denial disparities against the reference group, before and after adjustment | `results/f03/adjusted.parquet` | real:hmda, mart_hmda_applications |
| Denial rate by county, unadjusted and adjusted for the application mix | `results/f03/county.parquet` | real:hmda, mart_hmda_applications |
| The first reason lenders gave for a denial | `results/f03/denial_reasons.parquet` | real:hmda, mart_hmda_applications |
| What parity costs: the search for a less discriminatory alternative | `results/None` | real:baf, fraud_account validation report |
| Application fraud under the BAF suite's fairness protocol | `results/None` | real:baf, fraud_account validation report |
| Who the card model declines wrongly, by age band and gender | `results/None` | replayed, fraud_card validation report |
| Expected cost of fraud by decline threshold, test months | `results/f04/cost_curve.parquet` | replayed, fraud_card scored stream |
| What the desk could know, day by day | `results/f04/label_lag.parquet` | replayed, fraud_card scored stream |
| Precision and recall across thresholds, test months | `results/f04/pr_curve.parquet` | replayed, fraud_card scored stream |
| The investigator's view: alerted communities in the transfer network | `results/f05/network.json` | generated, Louvain communities over transfers between customers |
| What each rule finds, against the planted truth | `results/f05/rule_scorecard.parquet` | generated, packages/crime |
| Alerts by month and rule | `results/f05/alerts_monthly.parquet` | generated, packages/crime |
| Deposits by product | `results/f06/deposits_monthly.parquet` | generated, marts.mart_deposits_monthly |
| Checking accounts opened and closed each month | `results/f06/deposits_monthly.parquet` | generated, marts.mart_deposits_monthly |
| The policy rate, and what each product pays | `results/f06/rates.parquet` | generated, marts.mart_deposits_monthly |
| The retention list: expected balance at risk | `results/f06/retention_list.parquet` | generated, marts.mart_deposits_monthly |
| The capital ratio along each scenario | `results/f08/stress_paths.parquet` | real:frb_scenarios, marts.mart_scenarios and ledger_stress.link |
| Net interest income over twelve months, parallel rate shocks | `results/f08/nii_shocks.parquet` | generated, marts.mart_balance_sheet_monthly |
| Unsecured loans rolling into delinquency each quarter, along the 2026 scenarios | `results/f08/stress_paths.parquet` | real:frb_scenarios, marts.mart_scenarios and ledger_stress.link |
| Six month charge offs: forecast against what happened, by origin | `results/f09/backtest.parquet` | generated, marts.fct_loan_month |
| The next six months for the loans open today | `results/f09/forecast.parquet` | generated, marts.fct_loan_month |
| The collections queue: balance at risk times the chance of not curing | `results/f09/queue.parquet` | generated, marts.fct_loan_month |
| Cumulative recoveries after charge off | `results/f09/recoveries.parquet` | generated, marts.fct_loan_month |
| The fraud model's monitoring, week by week | `results/f10/fraud_weekly.parquet` | replayed, fraud_card |
| Score stability by application quarter, against the development quarters | `results/f10/pd_psi_by_quarter.parquet` | generated, pd_scorecard |
| Reported balance against the sum of postings, by account and month | `results/f11/reconciliation.parquet` | generated, f11 reconciliation |
| Net benefit of each candidate cutoff, on loans with observed outcomes | `results/f12/cutoff_options.parquet` | generated, pd_scorecard scores, loan outcomes, recoveries |
