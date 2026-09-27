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

## Fair lending

On the real New Jersey HMDA register, 2024 and 2025: 215,881 decided applications, 14.4% denied. The method, the controls and what the numbers can and cannot say are in `docs/fair-lending.md`.

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

Unadjusted, Essex County denies the most (18.5%) and Hunterdon the least (10.2%) against 14.4% for the state. Adjusted for each county's applications and lenders, Hudson still denies 1.31 times the denials its mix predicts. County is a map, never a model input: it is on the proxy list.

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

Debt to income ratio is the most common first reason, on 31.6% of denials. Credit history comes first on 21.0% of denials to Black applicants against 18.3% for white non Hispanic applicants, and credit history is exactly what the public file leaves out.

| Reason for denial | Denials | Share | Share, White non Hispanic | Share, Black | Share, Hispanic or Latino | Share, Asian |
|---|---:|---:|---:|---:|---:|---:|
| Debt to income ratio | 9,820 | 31.6% | 30.9% | 33.8% | 36.8% | 35.3% |
| Credit history | 5,150 | 16.6% | 18.3% | 21.0% | 14.4% | 7.4% |
| Credit application incomplete | 4,980 | 16.0% | 13.6% | 11.9% | 11.2% | 13.5% |
| Collateral | 4,931 | 15.9% | 18.3% | 15.5% | 15.2% | 18.2% |
| Other | 2,530 | 8.1% | 8.3% | 7.5% | 9.1% | 9.7% |
| Unverifiable information | 1,618 | 5.2% | 4.9% | 4.0% | 6.1% | 7.0% |
| Insufficient cash | 1,577 | 5.1% | 4.4% | 4.9% | 5.2% | 7.2% |
| Employment history | 429 | 1.4% | 1.3% | 1.4% | 1.9% | 1.6% |
| Mortgage insurance denied | 15 | 0.0% | 0.0% | 0.0% | 0.1% | 0.0% |

Every published model's features against the proxy list:

| Model | Features | Protected attributes or proxies among them |
|---|---:|---|
| aml_triage | 13 | none |
| fraud_account | 27 | none |
| fraud_card | 18 | none |
| pd_challenger | 13 | none |
| pd_scorecard | 8 | none |

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

### Application fraud on the BAF suite

At a 5% false positive rate the model finds 49.0% of fraudulent applications in the base variant and 49.3% in variant II. Genuine applicants aged 50 and over are flagged at 9.19% against 4.19% for the rest, a predictive equality of 0.46 (0.44 in variant II), though the model never sees age.

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

The model's own features predict whether an applicant is 50 or over with an AUROC of 0.782. Removing the strongest carriers of age one at a time moves the base variant's predictive equality from 0.46 to 0.57 and its recall from 49.0% to 44.2%. The model is kept and bounded to asking for documents, never to declining.

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

## Financial crime

The four rules fired 649 alerts, 7.9 per hundred thousand ledger entries, and found 362 of 422 complete planted episodes. Structuring is where the work is: 41.5% of its alerts are real, because cash intensive businesses deposit just under the threshold for honest reasons. The other three rules fired no false alerts on this generator, which a real program should not expect.

| Rule | Alerts | Precision | Complete episodes | Found | Recall | Posted in part | Alerts per 100k entries |
|---|---:|---:|---:|---:|---:|---:|---:|
| Structuring | 376 | 41.5% | 204 | 156 | 76.5% | 0 | 4.57 |
| Rapid movement | 100 | 100.0% | 100 | 100 | 100.0% | 0 | 1.22 |
| Round tripping | 90 | 100.0% | 24 | 24 | 100.0% | 19 | 1.09 |
| Mule fan in | 83 | 100.0% | 94 | 82 | 87.2% | 0 | 1.01 |

Source: generated, Harborline deposit accounts and their entries, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

The 43,318 accounts that pay other customers fall into 9,263 separate groups, mostly small circles of friends and family, and Louvain finds no finer structure inside any of them, so each group is one community. 12 of the 15 planted rings sit whole inside one community, and the round tripping rule fired on members of 10 of them, every ring with a trip that posted in full. Mule accounts show as stars: many outside senders, one wire out.

| Community | Accounts | Alerts | Share alerted | Planted accounts | Rules fired | Money inside |
|---:|---:|---:|---:|---:|---|---:|
| 0 | 25 | 15 | 20.0% | 5 | round_tripping | $730,800 |
| 11 | 14 | 12 | 28.6% | 4 | round_tripping | $493,756 |
| 10 | 15 | 4 | 26.7% | 4 | round_tripping | $269,814 |
| 3 | 20 | 8 | 20.0% | 4 | round_tripping | $431,068 |
| 2 | 22 | 8 | 18.2% | 4 | round_tripping | $272,630 |
| 1 | 23 | 16 | 17.4% | 4 | round_tripping | $613,443 |
| 13 | 11 | 9 | 27.3% | 3 | round_tripping | $300,847 |
| 9 | 17 | 6 | 17.6% | 3 | round_tripping | $257,653 |

The triage model, `aml_triage`, on the test months:

| Model | AUROC | Gini | Brier | ECE |
|---|---:|---:|---:|---:|
| This model | 1.000 | 1.000 | 0.0071 | 0.0155 |
| Base rate | 0.500 | 0.000 | 0.2601 | 0.1489 |
| The rules' own order | 0.788 | 0.576 | 0.1576 | 0.1276 |
| This model without cash history and branches | 0.997 | 0.994 | 0.0362 | 0.0751 |

Source: generated, Every alert the four rules fired on Harborline deposit accounts, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## Deposits and customers

Deposits stood at $930.6M in 2026-08, +13.2% since the first month. Checking is 49.0% of the total: the cheapest money the bank has, and the first to leave when a customer does.

The policy rate fell 2.58 points from 2024-08 to 2026-08. Savings passed on 0.38 of it (its offered beta is 0.38); time deposits passed on only 0.32 in the first year, because a certificate reprices only when it matures, and 0.66 by the end. Treasury's rate shocks use these betas.

| Product | Generator's beta | Recovered from the rate sheet | Within 0.02 | Paid rate beta, first year of cuts | Paid rate beta, whole cycle |
|---|---:|---:|---|---:|---:|
| Checking | 0.02 | 0.02 | yes | 0.01 | 0.01 |
| Savings | 0.38 | 0.38 | yes | 0.38 | 0.38 |
| Time deposits | 0.72 | 0.72 | yes | 0.32 | 0.66 |

Source: generated, Harborline deposit accounts, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

The largest depositors' share of deposits:

| Largest depositors | Customers | Share of deposits |
|---|---:|---:|
| Top 1% | 392 | 12.6% |
| Top 5% | 1,960 | 32.5% |
| Top 10% | 3,920 | 46.7% |

The 500 customers at the top of the list hold $114,622,517 and carry $9,442,588 of expected balance at risk, out of $61,088,783 across all 39,200 checking customers. The list is ordered by probability times balance, so a call goes to the relationship worth keeping. The attrition model reaches an AUROC of 0.583 on month ends it never saw, against a ceiling of 0.588 that the generator's own hazards reach with perfect knowledge of the year ahead.

| Customer | Probability of leaving within a year | Balances | Expected balance at risk | Why |
|---|---:|---:|---:|---|
| C037083 | 6.7% | $1,463,425 | $98,069 | checking balance; savings and time balances |
| C029680 | 19.5% | $362,451 | $70,606 | has complained; uses digital banking |
| C041637 | 5.5% | $1,271,418 | $70,198 | checking balance; savings and time balances |
| C044343 | 7.5% | $777,371 | $58,211 | uses digital banking; savings and time balances |
| C047468 | 7.9% | $709,516 | $55,974 | uses digital banking; savings and time balances |
| C040435 | 6.9% | $788,264 | $54,449 | checking balance; savings and time balances |
| C034336 | 9.0% | $574,618 | $51,818 | uses digital banking; savings and time balances |
| C002484 | 8.0% | $644,511 | $51,623 | uses digital banking; checking balance |
| C009648 | 18.3% | $279,663 | $51,287 | customer for under a year; uses digital banking |
| C035962 | 5.8% | $868,795 | $49,987 | checking balance; savings and time balances |
| C019831 | 9.2% | $534,437 | $48,949 | uses digital banking; time as a customer |
| C019661 | 7.6% | $634,302 | $47,978 | uses digital banking; savings and time balances |
| C040197 | 8.7% | $545,563 | $47,601 | uses digital banking; savings and time balances |
| C002401 | 20.5% | $231,661 | $47,550 | has complained; uses digital banking |
| C011480 | 37.3% | $121,097 | $45,227 | has complained; customer for under a year |

Source: generated, Harborline deposit accounts, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

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
| fraud_account | Application fraud on the BAF suite | f04 | 1 | sole | in use | 2026-08-31 | approved with conditions | 0.880 |
| aml_triage | Alert triage for transaction monitoring | f05 | 2 | sole | in use | 2026-08-31 | approved | 1.000 |
| attrition | Deposit customer attrition, twelve month horizon | f06 | 2 | sole | in use | 2026-08-31 | approved | 0.583 |

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
| 2026-09-27 | aml_triage | On months it never saw, the triage model put every alert that matched an injected typology ahead of every legitimate lookalike: an AUROC of one. | The report publishes the ranking without the two strongest features and the rules' own order as benchmarks, states that the measured quality is a property of the generator, and makes investigator dispositions the monitoring measure the model would be refit on before any real use. |
| 2026-09-27 | aml_triage | The mule, rapid movement and round tripping rules fired no false alerts on this data, so a model that only learned which rule fired would already rank most of the queue correctly. | A gate now measures the model within structuring alerts alone, where the rules' order carries no information, and the benchmark table includes ranking by each rule's development precision. |
| 2026-09-27 | fraud_account | customer_age is on the proxy list and never a feature, yet at the suite's threshold older applicants who are not fraudsters are flagged far more often than younger ones. If the model cannot see age, where does the gap come from? | The date of birth count is on the proxy list now, with its reason, so no model may use it. The report publishes a search for a less discriminatory alternative: the next strongest age carriers removed one at a time, with the recall each step costs and the parity it buys, on both variants. The model's use is bounded to asking for documents before an account opens, never to declining one, because a false flag then costs an applicant a delay rather than an account. |
| 2026-09-27 | fraud_account | Recall at a five percent false positive rate sets the threshold on the same months it reports. A bank has to fix its threshold before the applications arrive, and the false positive rate it then gets is whatever the new months give it. | The report and the page publish both: the suite's measure, and the recall, false positive rate and predictive equality on months 6 and 7 at the threshold fixed on month 5. The recall gate uses the fixed threshold, and a gate watches how far the realised false positive rate drifts from its target. |
| 2026-09-27 | attrition | The first split trained on every month end up to December 2024 and tested on the summer of 2025. A December 2024 label says whether the customer left by December 2025, which the bank could not have known when it scored the summer of 2025. | Training uses month ends September 2023 to February 2024, validation March to May 2024, and test June to August 2025, so every training and validation outcome was known before the first test month end. The gap is stated in the report beside the split. |
| 2026-09-27 | attrition | Sorted by probability alone, the top of the retention list fills with new customers holding a few hundred dollars. A retention call costs the same whoever answers. | The list is ranked by expected balance at risk. The report publishes, for the top tenth of the test months, the share of closers and the share of their balances found by each ordering, so the trade between the two is visible. |

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
