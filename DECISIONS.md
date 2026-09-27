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

## 2026-09-26: Complaint text comes from the Bureau's narratives archive

The CFPB stopped publishing complaint narratives on 14 August 2026 and moved every
previously published narrative into a FOIA reading room archive. The live database
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
