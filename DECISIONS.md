# Decisions

Dated entries, newest last. Entries marked **Challenge** are effective challenge
records: a question raised against a model or method during development, and what
changed because of it. The model validation reports quote them.

## 2026-09-26: Name the product `ledger`, name the bank Harborline Bank

`ledger` is the book of record, and the build is organised around the general
ledger reconciling to the cent. `teller` names one job, not the function.

The bank needed a name no insured institution carries. The FDIC BankFind search
returned a fuzzy hit for the first candidate, Larkfield, so it was dropped.
Harborline, Harbor Line and Harbourline returned nothing. The name is re-checked
against the full institution directory (active and inactive) by
`scripts/check_bank_name.py` on every CI run.

## 2026-09-26: New Jersey for the fair lending analysis, 2024 and 2025 HMDA

A bank's fair lending review covers the market it lends in. Harborline's footprint
is New Jersey, so the HMDA analysis uses the New Jersey loan application register
for the two most recent years published, 2024 and 2025, action taken 1 to 5
(originations, approvals not accepted, denials, withdrawals, incomplete files).
Purchased loans and preapproval requests are excluded because they are not
applications decided by the reporting lender.

## 2026-09-26: Reversal: complaint text comes from the Bureau's narratives archive, not its API

The plan was the database's filtered download, narratives included. The CFPB stopped
publishing complaint narratives on 14 August 2026 and moved every previously
published narrative into a FOIA reading room archive. The live database
still carries every complaint's metadata. So the complaints function takes volumes,
products, issues, company responses and the company benchmark from the live
database's search API, for the 24 complete months September 2024 to August 2026,
and takes narrative text from the archive's monthly export files. The page says so.

## 2026-09-26: The palette validator overruled three values in the brief

Run against the brief's values, `scripts/validate_palette.js` failed three things:

- Light slot 4, `#7A45D4`, sat 0.040 in OKLab lightness and 0.017 in chroma from slot
  3, under the 0.045 and 0.02 floors. Replaced with `#6C3FCB`, the same violet
  0.069 darker. Adjacent separation in light mode is now 11.6 for colour vision
  deficiency and 21.3 for normal vision.
- The dark diverging midpoint `#2A3040` carried 0.030 chroma, which reads as a
  third blue. Replaced with the neutral `#2C2F36` at 0.013.
- The two sequential steps nearest each surface fell under the 1.5:1 fill floor.
  The ramps now run seven steps each, and the map and heatmaps use those seven.

## 2026-09-26: The static site stands on its own; the API deploy waits

The desk, the scorecard studio and the case queue are designed around a live API.
The site is published first, from a committed bundle, with the fraud desk playing a
recorded replay of the stream and the studio scoring applicants in the browser from
the published scorecard table. Both are labelled as such on the page. The API is
built and tested against a real Postgres, and deploys to Fly with Neon when the
account side is ready, without changing the site.

## 2026-09-26: A zero cent entry is not an entry

The first contract run stopped on 1,110 deposit entries and one journal line whose
amounts rounded to zero: spending budgets split into card, bill and wire payments
could leave a remainder under half a cent. A core system never posts a zero, so the
generator no longer writes one, and the contract that caught it (`amount != 0`)
stays.

## 2026-09-26: Journals are built in whole cents

`test_every_month_of_postings_balances` failed about one run in six on identical
data. The September 2023 postings were one cent out of balance, and floating point
summation order decided which side of the tolerance they fell on. The opening
journal checked its unrounded total and then rounded each line. Journals are now
built in integer cents with any rounding residue on the balancing line, and every
ledger test sums as decimals and requires exactly zero. A tolerance had been hiding
a real break.

## 2026-09-26: The reconciliation found three breaks before it found the planted one

The first full reconciliation located the injected break (savings, March 2026,
$4,217.36) and three the generator had made by accident: installment loans and
mortgages originated in September 2023 counted twice, once in the opening journal
and again through their disbursements, and a monthly drift of about a dollar from
September 2025 onward, when the first 24 month loans matured with a few cents of
rounding left on the servicing record and no payment behind it. All three were
fixed in the generator. The reconciliation's clean pass test now runs on a bank with
no injected break and must find nothing at all.

## 2026-09-26: Nothing opens after the as of date

The back book generator opened a customer's card up to 400 days after the
relationship began, with no upper bound, which put 129 card accounts in September
and October 2026, after the window closes, some already carrying August statement
balances. It was found reading the staged loans table before writing the warehouse.
The generator no longer creates them, and a quarantine rule rejects any loan
originated after the as of date.

## 2026-09-26: Reversal: ledger ties are exact, not within five cents

The generator's first test of the deposit sub ledger against the ledger allowed a
difference of five cents per product and month, on the reasoning that floating
point sums drift. That reasoning was wrong for a ledger, and the tolerance is what
let the one cent opening journal break and the maturity drift through. Every tie is
now an equality of decimals: the dbt tests, the reconciliation and the generator's
own tests.

## 2026-09-26: Challenge (pd_scorecard): the scorecard under predicts the loosened vintages

**Raised:** On the validation months the scorecard's mean predicted default rate sat
well under the observed rate, while its rank ordering held up.

**Response:** The validation months are the two vintages written under the loosened
cutoff, and the test months carry the recession quarter. The hazard fit recovers a
vintage effect close to the generator's stated one, and no application
characteristic carries it, so a scorecard fitted on earlier vintages cannot see it.
That is a calibration problem, not a ranking problem, and a bank would treat it the
same way: keep the scorecard for decisions and adjust the probability used for loss.

**Changed:** Calibration became a non critical gate, so the report concludes
approved with a stated condition rather than approved, and expected loss in function 2
applies an observed to expected overlay by vintage instead of the raw scorecard
probability.

## 2026-09-26: Challenge (pd_scorecard): no lender drops prior delinquencies from a credit model

**Raised:** The fitted scorecard has no delinquency characteristic. Delinquencies in
the last 24 months fell under the information value floor and were dropped.

**Response:** In this book the characteristic is nearly empty (most applicants have
none) and carries little information once the bureau score is in the model, which
already reflects payment history. Forcing it in would add a characteristic whose
bins barely differ, and whose points would move with noise.

**Changed:** The published information value table now lists every candidate with the
reason it was kept or dropped, so a reviewer sees the decision instead of an absence,
and the challenger, which sees every candidate, confirms the characteristic adds
little.

## 2026-09-26: Challenge (pd_challenger): the first challenger was overfitting

**Raised:** The first fit's development AUROC was far above its validation AUROC.

**Response:** With fifteen leaves and a small minimum leaf, the trees were learning the
development months' noise; early stopping alone did not close the gap.

**Changed:** Seven leaves and a minimum of 150 loans per leaf. The development to
validation gap narrowed and the validation and test AUROC held.

## 2026-09-26: Challenge (pd_challenger): it beats the scorecard, so why not promote it

**Raised:** The challenger's test AUROC is above the champion's.

**Response:** The gain has to pay for what the bank gives up. A gradient boosted model
cannot state Regulation B reasons directly; declined applicants would still get
reasons computed from the scorecard, which means explaining one model's decision
with another model. A small gain does not buy that.

**Changed:** Promotion requires a test AUROC at least 0.01 above the champion's, stated
as a gate in the validation report, together with the stability and age band gates.

## 2026-09-26: Sparkov's time of day followed the date, and the wrapper corrects it

The first card fraud model stopped improving on validation after its first few trees
while its training loss kept falling, and its test predictions averaged many times
the fraud rate. The feature it leaned on hardest was the hour. Every genuine
transaction in September 2025 had been generated before noon and every one from May
2026 after it, and merchant categories came in monthly bands (gas stations in
September, home goods in June, travel in August). At the pinned commit, Sparkov's
`closest_rand_parallel` compares column 1 of its random array whatever column it is
asked to map, so the daypart and the category are drawn from the same number as the
date. The wrapper now replaces that one method at run time with the comparison the
code intends; Sparkov is otherwise unmodified, and data/PROVENANCE.md says so. The
stream was regenerated with the same seed.

## 2026-09-26: Challenge (fraud_card): the merchant history feature learned the calendar

**Raised:** The merchant features were a cumulative count of a merchant's labelled
transactions and a fraud rate over every label since the data began. Both grow or
settle with the calendar, so the same merchant looks different in March than in
August for no reason a fraud analyst would accept.

**Response:** A feature whose meaning drifts with elapsed time teaches a model the
calendar. On the desk it would also make a new merchant look risky forever and an old
one safe forever.

**Changed:** The merchant fraud rate now uses only labels that arrived in the trailing
90 days, smoothed toward the rate over the same window, and the raw volume count was
removed from the model.

## 2026-09-26: Challenge (fraud_card): the distant merchant rule was mostly noise

**Raised:** At 150 km the rule fired on roughly one transaction in thirty, at about
twice the base fraud rate. Every one of those is a review an analyst has to clear.

**Response:** Sparkov places merchants at random within a band around the cardholder,
so consecutive merchants are often far apart for genuine reasons. A rule that doubles
the base rate while flooding the queue costs more analyst time than it saves.

**Changed:** The threshold moved to 220 km, which cut the rule's volume by more than
an order of magnitude. Its precision is published in the validation report, and the
monitoring plan retires any rule that falls below twice the base rate.

## 2026-09-26: Challenge (fraud_card): nobody believes a card fraud AUROC this high

**Raised:** Once the stream was corrected, the model separates fraud from genuine
transactions almost perfectly on the test months.

**Response:** That is a property of the generator, not an achievement. Sparkov draws
fraudulent amounts, hours and categories from distributions that barely overlap with
genuine ones; real card fraud imitates genuine spending. What carries over to a real
desk is the machinery around the score: the cost based operating point, the queue
point, labels that arrive late, and precision that only counts what has been labelled.

**Changed:** The validation report and the desk page lead with cost and late labels,
state this limitation beside the discrimination figures, and the AUROC gate is not the
reason the model is approved.
