# The fraud desk: how the threshold is set, and what the desk can say about itself

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

The method behind f04, the `/desk` page and the `fraud_card` model. Every figure is
rendered from the manifest.

## What a decision costs

A decline on a genuine transaction costs the bank $12.00: the
interchange it does not earn and the call the customer makes. A missed fraud costs its
amount plus $35.00 for the investigation and the new
card. Both are assumptions stated in `config/ledger.yaml`, not measured costs, and changing
either moves the operating point; the slider on the desk shows by how much.

## The operating point

The threshold is the one that minimised expected cost on the validation months
(April and May 2026), and it is reported only on the test months
(June to August 2026), which it never saw.

False declines cost $12.00 each and missed fraud costs its amount plus $35.00. The threshold that minimised the sum on the validation months, 0.0503, costs $24,927 on the test months against $1,573,327 for approving everything. Accuracy would have chosen 0.6376 and cost $89,153.

| point | threshold | declined_or_queued | cost |
|---|---:|---:|---:|
| Cost minimum (operating point) | 0.0503 | 3,676 | $24,927 |
| Queue point | 0.2759 | 2,970 | not applicable |
| Accuracy maximum | 0.6376 | 2,659 | $89,153 |
| Approve everything | not applicable | 0 | $1,573,327 |

Source: replayed, Sparkov card transactions, September 2025 to August 2026, as of 2026-08-31.

The analyst queue holds alerts above a second, stricter threshold: the lowest whose
validation precision reached 90%, because an analyst's
hour is budgeted and every queued alert ends in a call to a customer.

## Late labels

A card fraud label exists only once the chargeback window of
60 days has passed.

On 2026-08-31, 200,569 of 472,370 scored decisions were still inside the 60 day chargeback window. Precision over the labelled ones was 73.4%. A figure that treated the unlabelled declines as mistakes would read 27.0%.

On the as of date the desk reports precision over labelled decisions only,
73.4%, and says how many decisions it cannot
yet judge. Counting every unlabelled decline as a mistake would have printed
27.0%, a number that looks like a crisis and is
an artefact of the calendar. A test rejects any precision computed over the window.

## The rules beside the model

Rules can send a transaction to review but never decline it alone. Each is kept only
while its precision on labelled months stays above twice the base rate.

| rule | fired | precision | recall |
|---|---:|---:|---:|
| First purchase over $500 in a category this card has never used | 88 | 100.0% | 3.1% |
| Three or more purchases on this card within 10 minutes | 272 | 12.1% | 1.2% |
| Merchant more than 220 km from this card's previous merchant within the hour | 521 | 1.7% | 0.3% |

## Who the errors fall on

At the operating point, genuine transactions of cardholders 60 and over are declined at 0.34% and those of cardholders under 25 at 0.20%, a ratio of 0.60. Sparkov generates age and gender, so they can be measured here; the model never sees either.

Application fraud has the same question with more at stake, because a false flag there
delays an account. On the BAF suite, measured under its own protocol:

At a 5% false positive rate the model finds 49.0% of fraudulent applications in the base variant and 49.3% in variant II. Genuine applicants aged 50 and over are flagged at 9.19% against 4.19% for the rest, a predictive equality of 0.46 (0.44 in variant II), though the model never sees age.

The model's own features predict whether an applicant is 50 or over with an AUROC of 0.782. Removing the strongest carriers of age one at a time moves the base variant's predictive equality from 0.46 to 0.57 and its recall from 49.0% to 44.2%. The model is kept and bounded to asking for documents, never to declining.

The full protocol, both variants and the search for a less discriminatory alternative
are in `report/validation/fraud_account.md`.

## The live desk and the recording

The API replays the scored test stream on a simulated clock: an asyncio task reading a
file and pushing server sent events, not a message bus. Each decision is written to the
audit log before any payload leaves the API. When the API is asleep, the page plays a
recording of the same stream in the browser and says so in a banner.
