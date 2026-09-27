# The model inventory

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

Every model the bank uses, with its tier, role, status and the conclusion of its last
validation. Each has a report in `report/validation/` with the same sections in the same
order, rendered from the manifest, and a report with a section missing does not render.

| Model | Title | Function | Tier | Role | Status | Last validated | Conclusion | Test AUROC |
|---|---|---|---|---|---|---|---|---:|
| pd_scorecard | Probability of default scorecard (champion) | f02 | 1 | champion | in use | 2026-08-31 | approved with conditions | 0.662 |
| pd_challenger | Probability of default challenger (monotone GBM) | f02 | 1 | challenger | validated | 2026-08-31 | not approved | 0.667 |
| fraud_card | Card transaction fraud (the desk's model) | f04 | 1 | sole | in use | 2026-08-31 | approved | 1.000 |
| fraud_account | Application fraud on the BAF suite | f04 | 1 | sole | in use | 2026-08-31 | approved with conditions | 0.880 |
| aml_triage | Alert triage for transaction monitoring | f05 | 2 | sole | in use | 2026-08-31 | approved | 1.000 |
| attrition | Deposit customer attrition, twelve month horizon | f06 | 2 | sole | in use | 2026-08-31 | approved | 0.583 |
| relief | Monetary relief on consumer complaints | f07 | 2 | sole | development | 2026-08-31 | not approved | 0.869 |
| cure | Cure within ninety days for delinquent loans | f09 | 2 | sole | in use | 2026-08-31 | approved | 0.787 |

Source: mixed, the model inventory, as of 2026-08-31.

## How a model is tiered

Materiality first, complexity as a tie breaker upward. A model that decides
automatically is tier one. A model that informs a decision a person makes is tier one if
its method is hard to inspect and tier two otherwise. Analytical and monitoring models
are tier three.

## What every model must show

Thirteen contract lines, each a sentence or two in the model's own report: how it was
trained, how its features are timed, calibrated, useful against a baseline that is not a
straw man, fair, gated, served, integrated, monitored, documented, bounded, validated and
explainable. Promotion gates are set in the training module before the model is
evaluated, and a model that fails a critical gate is not approved, whatever else it does.

## Challenges on record

17 effective challenges were raised and answered during
development, at least two for every model. Each names what was raised, the response, and
what changed; they are listed in each report and in `DECISIONS.md`.
