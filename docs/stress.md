# Treasury and stress: method, simplifications, and what the numbers can say

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

The method behind f08 and the `/treasury` page. These are illustrative projections
on a fictional bank in the shape of the supervisory exercise, not the exercise.

## Net interest income under rate shocks

A repricing gap over 12 months. Each position
reprices some share of its balance within the horizon, weighted by how much of the
horizon is left when it does: cash and card loans at once; installment loans and
mortgages as they run off (45.2% and 26.3%
of their books over the last year); securities as an even
5.0 year ladder; certificates as they mature
(86.0% within the year). Deposits move by the betas recovered in
f06, and no rate falls below its floor.

| Parallel shock | Change in net interest income | Share of the last twelve months | From assets | From deposits |
|---:|---:|---:|---:|---:|
| -200 | -$175,123 | -0.3% | -$4,029,084 | $3,853,960 |
| -100 | -$87,562 | -0.2% | -$2,014,542 | $1,926,980 |
| 100 | -$3,490 | 0.0% | $2,014,542 | -$2,018,032 |
| 200 | -$6,981 | 0.0% | $4,029,084 | -$4,036,064 |

Source: generated, Harborline's balance sheet as of 2026-08, seed 20260831, as of 2026-08-31.

The balance sheet is held flat and customers do not change behaviour with rates. Economic
value of equity is not measured.

## The macro link

The log odds of a current unsecured loan rolling thirty days past due in a month, on
unemployment, house price growth, the loose underwriting vintages, months on book and the
product, fitted on 675,353 loan months. The generator's stated
sensitivity is 0.30 per point of unemployment and the link recovers
0.215 (0.186 to
0.244): within the stated tolerance of 0.10,
and attenuated, because a bank never sees the latent risk score the generator uses. No
scenario is projected from a link that fails this check.

| Term | Coefficient | Low | High |
|---|---:|---:|---:|
| Intercept | -4.782 | -4.847 | -4.718 |
| Unemployment, per point above four | 0.215 | 0.186 | 0.244 |
| House price growth, per point a year | -0.008 | -0.016 | 0.000 |
| The loose underwriting vintages | 0.439 | 0.385 | 0.493 |
| Card rather than installment | 0.877 | 0.827 | 0.927 |
| Six to eleven months on book | 0.417 | 0.355 | 0.480 |
| Twelve to twenty three months on book | 0.236 | 0.173 | 0.299 |
| Two years or more on book | -0.067 | -0.129 | -0.005 |

## The supervisory scenarios

The Federal Reserve's 2026 baseline and severely adverse scenarios,
applied as changes from their jump off quarter to the bank's own starting unemployment of
5.0, for 9 quarters. Losses follow the roll
into delinquency by a quarter, through each product's observed conversion to charge off
and its loss given default; intervals come from the link's covariance.

| Scenario | Peak unemployment, bank | Losses over 9 quarters | Low | High | Share of loans | Capital ratio at its lowest | Low | Capital ratio after 9 quarters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 5.1 | $27.2M | $27.2M | $27.2M | 3.8% | 19.8% | 19.8% | 28.8% |
| Severely adverse | 10.5 | $59.8M | $55.9M | $63.9M | 8.3% | 19.8% | 19.8% | 21.7% |

The ratio starts at 19.8%. Severely adverse losses peak at $8.6M a quarter, while pre provision revenue, held at its last twelve months of $8.2M a quarter and moved by the scenario's short rate, falls no lower than $7.7M, so the ratio ends the 9 quarters at 21.7% and never falls below where it started. No tax, dividends or balance sheet growth; illustrative projections on a fictional bank in the shape of the supervisory exercise, not the exercise.

## Liquidity

High quality liquid assets over thirty day outflows at the stated run rates of
10% for checking, 10% for
savings and 5% for time deposits: 378%, and
180% if the largest one percent of depositors also left in full.
Not the regulatory ratio: no inflows, no level two haircuts, no committed lines.
