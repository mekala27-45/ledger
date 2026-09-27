# Financial crime: the rules, the truth they are graded against, and the queue

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

The financial crime function, f05, and the `/crime` page.

## The typologies and their lookalikes

The generator plants four typologies in the deposit sub ledger with known membership, and writes legitimate customers who look like them on the rule's own terms:

- **Structuring**: cash deposits just under the reporting threshold of $10,000, over days and often across branches. Lookalike: cash intensive businesses that deposit near the threshold every week.
- **Rapid movement**: a large wire in and nearly all of it out again within hours. Lookalike: large wires for home purchases.
- **Mule**: many small payments in from unrelated senders, then one transfer out. Lookalike: people who split rent and bills with several friends.
- **Round tripping**: money that goes around a ring of accounts and comes home at about the same size.

## The rules

One rule per typology, stated in `rules/aml_typologies.yaml` in the words an investigator reads on the alert, with thresholds in `config/ledger.yaml`:

- Structuring: at least three cash deposits between $8,000 and the reporting threshold within 10 days, together above it.
- Rapid movement: a wire in of at least the reporting threshold, with most of it gone within 24 hours.
- Mule: payments in from at least 8 different senders within 14 days, then most of the money out in one transfer.
- Round tripping: a cycle of at most 5 accounts within 14 days, each hop within a tenth of the others' size.

## Graded against the truth, and only the truth that posted

Every alert is matched to the planted episodes on the same account, of the same kind, overlapping in time. Recall counts only episodes whose every entry reached the ledger: the generator drops entries that would land after an account closed or in the last days of a month, and a round trip with a missing hop is not a round trip. Precision counts every alert.

| Rule | Alerts | Precision | Complete episodes | Found | Recall | Posted in part | Alerts per 100k entries |
|---|---:|---:|---:|---:|---:|---:|---:|
| Structuring | 376 | 41.5% | 204 | 156 | 76.5% | 0 | 4.57 |
| Rapid movement | 100 | 100.0% | 100 | 100 | 100.0% | 0 | 1.22 |
| Round tripping | 90 | 100.0% | 24 | 24 | 100.0% | 19 | 1.09 |
| Mule fan in | 83 | 100.0% | 94 | 82 | 87.2% | 0 | 1.01 |

Source: generated, Harborline deposit accounts and their entries, September 2023 to August 2026, seed 20260831, as of 2026-08-31.

## The queue

The alerts are worked in the order `aml_triage` sets; its validation report is at `report/validation/aml_triage.md`. The model orders the queue and does nothing else: every alert stays in it until an investigator closes it.

## The network

Accounts are nodes and transfers between different customers are edges, weighted by the money that moved. The 43,318 accounts that pay other customers fall into 9,263 separate groups, mostly small circles of friends and family, and Louvain finds no finer structure inside any of them, so each group is one community. 12 of the 15 planted rings sit whole inside one community, and the round tripping rule fired on members of 10 of them, every ring with a trip that posted in full. Mule accounts show as stars: many outside senders, one wire out.

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

## What is not here

No suspicious activity report is filed, drafted or implied. Monitoring alerts are published as a ranked list; the API's case endpoints serve the fraud desk's alerts.
