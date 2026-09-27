# ledger: results

Every figure below is rendered from `results/manifest.json`, written by the pipeline run with seed 20260831 and data to 2026-08-31. CI re-renders this file and fails if a single character differs. Each table carries the backend and population that produced it: `generated` is the seeded bank, `replayed` is the scored card stream, and `real:` names a public dataset.

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

## The bank at a glance

Harborline Bank closed 2026Q2 with total assets of $1,033.6M, gross loans of $720.0M and deposits of $930.6M. Net income over the trailing twelve months was $13.4M.

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

Net interest margin was 5.60% in 2026Q2, up 5 basis points on the quarter, and nonperforming loans fell 15 basis points to 0.49%. The shaded band is each ratio's trailing twelve month mean plus or minus two standard deviations.

Source: generated, Harborline Bank general ledger, seed 20260831, as of 2026-08-31.

What moved, ranked by dollar materiality and written by a rules engine from the metric layer:

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

## Known parameter recovery

The generator states the loan book's risk structure; the pipeline has to recover it before any credit figure is used.

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

## The scorecard

Every candidate characteristic with its information value, and why each dropped one was dropped:

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

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

The scorecard, points per bin, with 600 points at odds of 30 to one and 20 points to double the odds:

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

The same engine on the UCI credit card accounts, a real default label:

| characteristic | iv | kept |
|---|---:|---|
| pay_status_1 | 0.843 | kept |
| months_delinquent_6m | 0.837 | WoE correlation with pay_status_1 above the ceiling |
| pay_status_2 | 0.536 | coefficient sign reversed in the joint fit |
| pay_status_3 | 0.423 | kept |
| pay_amt_1 | 0.194 | kept |
| limit_bal | 0.194 | kept |
| payment_ratio_avg | 0.155 | kept |
| payment_ratio_1 | 0.149 | coefficient sign reversed in the joint fit |
| bill_growth_6m | 0.065 | kept |
| utilization_1 | 0.057 | kept |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

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

The first adverse action reason on declined test applications:

| reason | declines | share |
|---|---:|---:|
| Proportion of balances to credit limits on revolving accounts is too high | 1,539 | 61.1% |
| Credit history reported by the credit bureau is insufficient or delinquent | 680 | 27.0% |
| Income insufficient for amount of credit requested | 284 | 11.3% |
| Length of employment | 14 | 0.6% |

## Champion and challenger

| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 0.667 | 0.334 | 0.0624 | 0.0279 |
| Champion scorecard | 0.662 | 0.324 | 0.0626 | 0.0286 |
| Logistic on raw characteristics | 0.668 | 0.336 | 0.0624 | 0.0285 |
| Base rate | 0.500 | 0.000 | 0.0641 | 0.0307 |

Source: generated, booked installment loans with an observed outcome, seed 20260831, as of 2026-08-31.

The challenger ranks 0.005 AUROC better, agrees with the champion's ranking at 0.962, and was not approved for promotion. The gates it was held to are in its validation report.

## Consumer lending

The two vintages written under the loosened cutoff (2024Q4 and 2025Q1) reached 10.4% cumulative default by twelve months on book, against 4.0% for the vintages before them. Each curve stops where its youngest loan's history ends; nothing is extrapolated.

Source: generated, Harborline installment loans, seed 20260831, as of 2026-08-31.

A current loan rolls to 30 days past due with probability 1.46% a month; once there it rolls on to 60 with probability 54.6% and cures with 42.2%. The diagonal dominates every row, as it must in a book that mostly pays.

Source: generated, Harborline installment loans, seed 20260831, as of 2026-08-31.

Expected loss on the open installment book, $8,409,265 on $152.1M of exposure (5.53%), with loss given default of 79.6% from the generated recoveries:

| Score band | Loans | Exposure | PD (with overlay) | LGD | Expected loss | EL rate |
|---|---:|---:|---:|---:|---:|---:|
| under 560 | 371 | $4.6M | 23.69% | 79.6% | $889,783 | 19.40% |
| 560 to 599 | 7,032 | $71.2M | 9.82% | 79.6% | $5,787,865 | 8.13% |
| 600 to 639 | 6,701 | $62.4M | 3.16% | 79.6% | $1,625,988 | 2.61% |
| 640 and over | 1,724 | $14.0M | 0.91% | 79.6% | $105,629 | 0.75% |

Source: generated, Harborline installment loans, seed 20260831, as of 2026-08-31.

A CECL style lifetime illustration, simplified: $19,055,866 on the open book.

| Vintage | Exposure | 12 month PD | Lifetime PD | Macro factor | Lifetime loss |
|---|---:|---:|---:|---:|---:|
| 2023Q3 | $0.8M | 4.24% | 11.46% | 0.89 | $63,901 |
| 2023Q4 | $2.9M | 3.33% | 9.01% | 0.89 | $185,780 |
| 2024Q1 | $4.2M | 2.95% | 7.98% | 0.89 | $240,331 |
| 2024Q2 | $5.2M | 3.51% | 9.49% | 0.89 | $348,967 |
| 2024Q3 | $6.7M | 4.83% | 13.07% | 0.89 | $622,187 |
| 2024Q4 | $8.8M | 9.07% | 24.55% | 0.89 | $1,541,971 |
| 2025Q1 | $11.0M | 10.04% | 27.17% | 0.89 | $2,119,799 |
| 2025Q2 | $12.5M | 6.39% | 17.28% | 0.89 | $1,534,273 |
| 2025Q3 | $15.4M | 4.47% | 12.10% | 0.89 | $1,327,532 |
| 2025Q4 | $18.8M | 6.56% | 17.74% | 0.89 | $2,369,630 |
| 2026Q1 | $21.2M | 6.86% | 18.56% | 0.89 | $2,791,305 |
| 2026Q2 | $25.6M | 6.92% | 18.72% | 0.89 | $3,409,377 |
| 2026Q3 | $19.0M | 6.85% | 18.54% | 0.89 | $2,500,814 |

Source: generated, Harborline installment loans, seed 20260831, as of 2026-08-31.

Portfolio limits:

| Limit | Measured | Limit value | Status |
|---|---:|---:|---|
| Loosened vintages' share of installment balances | 13.03% | 35.00% | within |
| Installment balances 30 or more days past due | 2.58% | 4.00% | within |
| Nonperforming loans to gross loans | 0.54% | 1.00% | within |
| Mortgages' share of gross loans | 72.02% | 75.00% | within |

## Time to default

Twelve months after origination, 98.6% of loans scored 640 and over have not defaulted, against 82.7% of those under 560. The Cox model's proportional hazards test is published beside it.

| Covariate | Hazard ratio | 95% low | 95% high | PH test p value |
|---|---:|---:|---:|---:|
| Score, per 20 points | 0.595 | 0.570 | 0.621 | 0.990 |
| Loosened vintage | 1.960 | 1.761 | 2.182 | 0.003 |
| Unemployment at origination, per point | 1.120 | 1.043 | 1.201 | 0.016 |

Source: generated, booked installment loans, seed 20260831, as of 2026-08-31.

Loans at risk by months since origination:

| Score band | At risk at 0 | 6 | 12 | 18 | 24 |
|---|---:|---:|---:|---:|---:|
| under 560 | 587 | 428 | 294 | 189 | 77 |
| 560 to 599 | 9,893 | 7,214 | 4,805 | 2,945 | 1,538 |
| 600 to 639 | 8,782 | 6,464 | 4,368 | 2,793 | 1,616 |
| 640 and over | 2,216 | 1,656 | 1,174 | 756 | 446 |

## The fraud desk

False declines cost $12.00 each and missed fraud costs its amount plus $35.00. The threshold that minimised the sum on the validation months, 0.0503, costs $24,927 on the test months against $1,573,327 for approving everything. Accuracy would have chosen 0.6376 and cost $89,153.

| point | threshold | declined_or_queued | cost |
|---|---:|---:|---:|
| Cost minimum (operating point) | 0.0503 | 3,676 | $24,927 |
| Queue point | 0.2759 | 2,970 | not applicable |
| Accuracy maximum | 0.6376 | 2,659 | $89,153 |
| Approve everything | not applicable | 0 | $1,573,327 |

Source: replayed, Sparkov card transactions, September 2025 to August 2026, as of 2026-08-31.

At the operating point the desk declines with precision 74.8% and recall 97.6%; the queue point narrows to precision 89.7% for the analyst queue.

| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 1.000 | 0.999 | 0.0010 | 0.0002 |
| Base rate | 0.500 | 0.000 | 0.0092 | 0.0031 |
| Logistic on the same features | 0.933 | 0.866 | 0.0053 | 0.0015 |

On 2026-08-31, 200,569 of 472,370 scored decisions were still inside the 60 day chargeback window. Precision over the labelled ones was 73.4%. A figure that treated the unlabelled declines as mistakes would read 27.0%.

Source: replayed, Sparkov card transactions, June to August 2026, as of 2026-08-31.

Fairness at the operating point, by the demographic fields Sparkov generates:

| Group | N | Event rate | Mean score | Calibration gap | Auroc | Flag rate | Fpr | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F | 155,702 | 0.95% | 0.96% | 0.0% | 0.999 | 1.27% | 0.36% | 96.4% |
| M | 147,699 | 0.90% | 0.94% | 0.0% | 1.000 | 1.14% | 0.26% | 98.9% |
| 25 to 39 | 93,649 | 0.75% | 0.75% | 0.0% | 0.999 | 1.00% | 0.29% | 95.6% |
| 40 to 59 | 116,789 | 0.88% | 0.90% | 0.0% | 0.999 | 1.19% | 0.33% | 97.1% |
| 60 and over | 63,009 | 1.27% | 1.33% | +0.1% | 1.000 | 1.59% | 0.34% | 99.4% |
| under 25 | 29,954 | 0.96% | 0.98% | 0.0% | 1.000 | 1.16% | 0.20% | 99.7% |

The lowest false positive rate across age bands is 0.60 of the highest.

The desk's rules, on the labelled test months:

| rule | fired | precision | recall |
|---|---:|---:|---:|
| First purchase over $500 in a category this card has never used | 88 | 100.0% | 3.1% |
| Three or more purchases on this card within 10 minutes | 272 | 12.1% | 1.2% |
| Merchant more than 220 km from this card's previous merchant within the hour | 521 | 1.7% | 0.3% |

## Controls

786 of 792 account months tie to the cent. The one break is savings deposits, account 2010, first appearing in 2026-03 at $4,217.36 and carried unchanged into every later month: one break, located, not 6. Every posting traces to a sub ledger transaction.

| Account | First month | Amount | Months carried | Comparison | Finding |
|---|---|---:|---:|---|---|
| 2010 | 2026-03 | $4,217.36 | 6 | reported vs postings | the injected break, located |

Source: generated, Harborline general ledger, 22 accounts by 36 months, seed 20260831, as of 2026-08-31.

Every data quality rule, with the injected defects held to their injected counts:

| Rule | Table | Severity | Rows checked | Rows hit | Injected | Finding |
|---|---|---|---:|---:|---:|---|
| application income missing | loan applications | flag | 36,210 | 0 | not applicable |  |
| loan opened after as of | loans | quarantine | 40,288 | 0 | not applicable |  |
| loan balance negative | loan performance | quarantine | 854,389 | 0 | not applicable |  |
| transfer without counterparty | deposit entries | flag | 8,229,331 | 1,721 | 1,721 | caught at the injected count |
| entry after as of | deposit entries | quarantine | 8,229,331 | 0 | not applicable |  |
| balance does not roll | deposit balances | flag | 2,127,521 | 212 | 212 | caught at the injected count |
| posting duplicate | gl postings | quarantine | 17,990,726 | 7,193 | 7,193 | caught at the injected count |
| posting zero amount | gl postings | quarantine | 17,990,726 | 0 | not applicable |  |
| card txn nonpositive | card transactions | quarantine | 1,077,220 | 0 | not applicable |  |
| hmda exempt value | hmda lar | flag | 609,413 | 9,864 | not applicable |  |
| hmda income not available | hmda lar | flag | 609,413 | 49,974 | not applicable |  |
| hmda ltv not available | hmda lar | flag | 609,413 | 171,322 | not applicable |  |
| cfpb response in progress | cfpb narratives | flag | 46,084 | 2 | not applicable |  |
| uci undocumented code | uci default | flag | 30,000 | 399 | not applicable |  |
| baf missing marker | baf | flag | 600,000 | 564,284 | not applicable |  |
| bls month unavailable | macro monthly | flag | 116 | 1 | not applicable |  |

Source: mixed, every staged table, as of 2026-08-31.

The warehouse passed 210 of 210 dbt tests over 62 models. The identifier scan found 0 card numbers, Social Security numbers or generator person names across 30 staged tables, and the bank's name matches none of 27,834 FDIC institutions.

## Model risk

| Model | Title | Function | Tier | Role | Status | Last validated | Conclusion | Test AUROC |
|---|---|---|---|---|---|---|---|---:|
| pd_scorecard | Probability of default scorecard (champion) | f02 | 1 | champion | in use | 2026-08-31 | approved with conditions | 0.662 |
| pd_challenger | Probability of default challenger (monotone GBM) | f02 | 1 | challenger | validated | 2026-08-31 | not approved | 0.667 |
| fraud_card | Card transaction fraud (the desk's model) | f04 | 1 | sole | in use | 2026-08-31 | approved | 1.000 |

Source: mixed, the model inventory, as of 2026-08-31.

The worst quarter's population stability index is 0.005 (2026Q3), against a warning line at 0.10 and a breach at 0.25. Stability says the applicants look alike; it says nothing about whether they default alike, which is why calibration is monitored separately as outcomes mature.

Score stability is measurable the day a transaction is scored; discrimination is not. For the first 8 weeks of the test months no test transaction had cleared the 60 day chargeback window, so the model's AUROC on the new months could not be computed at all. That gap is the monitoring lag, and the plan says so rather than filling it.

The effective challenge log:

| Date | Models | Challenge | What changed |
|---|---|---|---|
| 2026-09-26 | pd_scorecard | On the validation months the scorecard's mean predicted default rate sat well under the observed rate, while its rank ordering held up. | Calibration became a non critical gate, so the report concludes approved with a stated condition rather than approved, and expected loss in function 2 applies an observed to expected overlay by vintage instead of the raw scorecard probability. |
| 2026-09-26 | pd_scorecard | The fitted scorecard has no delinquency characteristic. Delinquencies in the last 24 months fell under the information value floor and were dropped. | The published information value table now lists every candidate with the reason it was kept or dropped, so a reviewer sees the decision instead of an absence, and the challenger, which sees every candidate, confirms the characteristic adds little. |
| 2026-09-26 | pd_challenger | The first fit's development AUROC was far above its validation AUROC. | Seven leaves and a minimum of 150 loans per leaf. The development to validation gap narrowed and the validation and test AUROC held. |
| 2026-09-26 | pd_challenger | The challenger's test AUROC is above the champion's. | Promotion requires a test AUROC at least 0.01 above the champion's, stated as a gate in the validation report, together with the stability and age band gates. |
| 2026-09-26 | fraud_card | The merchant features were a cumulative count of a merchant's labelled transactions and a fraud rate over every label since the data began. Both grow or settle with the calendar, so the same merchant looks different in March than in August for no reason a fraud analyst would accept. | The merchant fraud rate now uses only labels that arrived in the trailing 90 days, smoothed toward the rate over the same window, and the raw volume count was removed from the model. |
| 2026-09-26 | fraud_card | At 150 km the rule fired on roughly one transaction in thirty, at about twice the base fraud rate. Every one of those is a review an analyst has to clear. | The threshold moved to 220 km, which cut the rule's volume by more than an order of magnitude. Its precision is published in the validation report, and the monitoring plan retires any rule that falls below twice the base rate. |
| 2026-09-26 | fraud_card | Once the stream was corrected, the model separates fraud from genuine transactions almost perfectly on the test months. | The validation report and the desk page lead with cost and late labels, state this limitation beside the discrimination figures, and the AUROC gate is not the reason the model is approved. |

## The board's decision

| Cutoff | Loans declined (+) or added (-) | Defaults among them | Losses avoided | Margin forgone | Net benefit |
|---:|---:|---:|---:|---:|---:|
| 560 | -2,333 | -287 | -$3,096,989 | -$2,900,496 | -$196,493 |
| 580 | 0 | 0 | $0 | $0 | $0 |
| 600 | 3,806 | 259 | $2,669,791 | $4,311,147 | -$1,641,356 |
| 620 | 7,038 | 414 | $4,249,056 | $7,587,812 | -$3,338,757 |
| 640 | 9,085 | 461 | $4,691,778 | $9,450,846 | -$4,759,067 |

Source: generated, booked installment loans with an observed twelve month outcome, seed 20260831, as of 2026-08-31.

The current cutoff of 580 beats every alternative on loans with observed outcomes. Lowering it to 560 would have added 2,333 loans and lost $196,493 net; raising it to 600 would have forgone $1,641,356 more margin than it saved in losses.

## Limitations

- The customers, accounts, loans, ledger and card stream are generated. Their structure is stated in the generator and recovered by the pipeline, which is what makes them testable, and it is also why no figure about them describes a real bank.
- The card fraud model's discrimination is a property of the Sparkov generator. The cost curve, the late label analysis and the subgroup audit are the parts that transfer.
- The scorecard's calibration fails on the loosened and recession vintages; the lending figures carry an observed to expected overlay for it and the validation report states the condition.
- The capital ratio uses stated, simplified risk weights, and the CECL figure is an illustration of the method without qualitative factors, reversion or prepayment.
- The peer benchmark compares a generated bank with real ones. The peers' figures are the FDIC's; the comparison is illustrative.
