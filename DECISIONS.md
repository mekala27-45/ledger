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

## 2026-09-27: A negative number lost its minus sign in print

The site formats numbers in the browser, so a test now runs the site's formatter and
the pipeline's over the same grid of values and requires identical text. Its first
run failed, and the failure was in the pipeline, not the site. The Python formatter
cleaned up negative zero with a string replacement of `-0.00`, which also matched the
start of any negative number between minus one cent and zero printed to more
decimals. The scorecard's validation report listed the gate "Test AUROC no more than
0.02 below the logistic benchmark" as measured at 0.0063 when the value was -0.0063.
The gate passed either way, but the report said the scorecard beat the benchmark when
it trails it slightly. A value now loses its sign only when it rounds to zero in the
digits printed, both formatters round half to even on the exact binary value, and
the parity test holds them together.

## 2026-09-27: The proportional hazards test gave different answers on the same data

Re-running the lending function without changing any input moved the Cox model's
proportional hazards p value for unemployment at origination from 0.28 to 0.04: one
run said the assumption held, the next that it failed. The test's rank time
transform numbers tied event times in row order, loan durations are whole months so
nearly every event time is tied, and the warehouse returns rows in no fixed order.
The test now uses the Kaplan Meier transform, the default in R's `cox.zph`, which
gives tied times the same value, and the input is sorted by loan. Two consecutive
runs now publish identical p values, and the loosened vintage and unemployment
effects both fail the assumption, which the lending page says plainly: their hazard
ratios are averages over loan age.

## 2026-09-27: The explorer ships Arrow, not parquet

The first version of the in-browser SQL explorer loaded the warehouse extracts as
parquet. DuckDB-WASM reads parquet through an extension it downloads on first use
from DuckDB's own servers, so a page that promised nothing leaves the browser would
have fetched code from a third party, and in a locked down network it failed
outright. The extracts are now Arrow IPC streams, which DuckDB-WASM inserts natively.
The page fetches nothing but its own files.

## 2026-09-27: The threshold slider disagreed with the model at the operating point

The desk's slider recomputes precision and recall from a histogram of test scores.
Set to the operating point it read 92.1% precision and 93.1% recall, where the
model's report says 74.8% and 97.6%. The histogram's bins came from evenly spaced
quantiles, so above the 99th percentile, where every decline happens, one bin held
over a thousand transactions and the operating point fell inside one. The histogram
is now built by the desk function from the scored test months, with fine bins above
the 99th percentile and the operating and queue points as exact edges, and a test
requires the histogram to reproduce the flagged count, the frauds caught and the
cost at both points to the transaction.

## 2026-09-27: The identifier scan read decimals as card numbers

Once the site bundle and the model outputs were in its path, the identifier scan
failed on hundreds of "card numbers", every one the fractional digits of a float in a
JSON file, sixteen or seventeen digits that happened to pass the Luhn check. The scan
now ignores a digit run that follows a decimal point, a test pins that a float's
fraction is not a card while a card number at the end of a sentence still is, and the
planted card number test still fails the scan as it should.

## 2026-09-27: The fair lending model would not converge until two levels were folded

The first adjusted fit on the New Jersey register ran its hundred Newton iterations
without converging, and the odds ratios it printed looked reasonable, which is the
dangerous case. Five applications carried HMDA's exempt code for the underwriting
system, all approved, so that level's coefficient was heading to minus infinity. A
few mid sized lenders had denied nobody, with the same effect on their fixed effects.
Exempt and other rare underwriting codes now join HMDA's own "other" code, a lender
gets its own fixed effect only with at least ten of each outcome, and the fit refuses
to publish anything unless the optimiser reports convergence.

## 2026-09-27: A rate ratio is not an odds ratio

The first draft of the fair lending callout said Black applicants were denied at 2.24
times the rate of white non Hispanic applicants and that adjustment brought the gap
down to 1.76. The first number is a ratio of rates and the second a ratio of odds,
and with denial rates this high the two scales differ: the unadjusted odds ratio is
2.63. The callout, the board pack and the chart now compare odds ratio with odds
ratio, and the unadjusted rate ratio is kept only in the table where it is labelled.

## 2026-09-27: An injected episode that never posted is not a missed one

The first typology scorecard found ten of forty three round trips. The generator's
truth table records every episode it planned, but its posting simulation drops entries
that would land after an account closed or in the last days of a month, so nineteen
round trips posted with a hop missing and fifty two episodes of other kinds posted
nothing at all. A ring with a missing hop is not a round trip, and no monitoring system
could find money that never moved. Recall is now measured on episodes whose every entry
posted, the partial ones are counted beside it, and the round tripping rule finds every
complete trip. Counting one alert per ring rather than per trip had hidden the rest.

## 2026-09-27: Challenge (aml_triage): it ranks every true alert above every false one

**Raised:** On months it never saw, the triage model put every alert that matched an
injected typology ahead of every legitimate lookalike: an AUROC of one.

**Response:** The generator writes its lookalikes and its criminals from separate
recipes. A cash intensive business deposits cash every week at one branch; a structurer
is new to cash and spreads deposits across several branches. Removing the cash history
and the branch count still leaves the alert size, its entry count and the account's
earlier alerts, and the separation survives, so it is not one leaked column. It is two
synthetic populations that do not overlap. A real program's labels are investigator
dispositions, which are noisier and arrive late.

**Changed:** The report publishes the ranking without the two strongest features and
the rules' own order as benchmarks, states that the measured quality is a property of
the generator, and makes investigator dispositions the monitoring measure the model
would be refit on before any real use.

## 2026-09-27: Challenge (aml_triage): three rules are never wrong here, so any order looks good

**Raised:** The mule, rapid movement and round tripping rules fired no false alerts on
this data, so a model that only learned which rule fired would already rank most of
the queue correctly.

**Response:** Pooled over all four rules, AUROC mostly rewards putting those three
rules' alerts first, which each rule's own precision on the development months already
does. The only alerts where order is a real question are structuring alerts, where the
rule's precision is under half.

**Changed:** A gate now measures the model within structuring alerts alone, where the
rules' order carries no information, and the benchmark table includes ranking by each
rule's development precision.

## 2026-09-27: The BAF model trains on one month less than the suite

The suite's protocol trains on months 0 to 5 and tests on months 6 and 7. fraud_account
trains on months 0 to 4 and holds month 5 back, because something has to choose the
tree count and the threshold a bank would actually deploy, and choosing either on the
test months would make the reported recall a best case. The cost is one month of
training data; the benefit is that every number in the report comes from months the
model and its threshold never saw.

## 2026-09-27: Challenge (fraud_account): leaving age out does not make the model blind to age

**Raised:** customer_age is on the proxy list and never a feature, yet at the suite's
threshold older applicants who are not fraudsters are flagged far more often than
younger ones. If the model cannot see age, where does the gap come from?

**Response:** From the other features. A model trained to predict fifty and over from
the fraud model's own features separates the two groups well, and the strongest single
carrier was date_of_birth_distinct_emails_4w: a count taken by grouping applications on
the applicant's date of birth, so its value depends on how common the applicant's birth
year is among applicants. Employment status, housing status and time at the current
address come next, and each is also a legitimate fraud signal.

**Changed:** The date of birth count is on the proxy list now, with its reason, so no
model may use it. The report publishes a search for a less discriminatory alternative:
the next strongest age carriers removed one at a time, with the recall each step costs
and the parity it buys, on both variants. The model's use is bounded to asking for
documents before an account opens, never to declining one, because a false flag then
costs an applicant a delay rather than an account.

## 2026-09-27: Challenge (fraud_account): the suite's recall is measured at a threshold set on the test months

**Raised:** Recall at a five percent false positive rate sets the threshold on the same
months it reports. A bank has to fix its threshold before the applications arrive, and
the false positive rate it then gets is whatever the new months give it.

**Response:** The suite's measure is right for comparing models with each other and
with the published results, and wrong as a statement of what the bank would see.

**Changed:** The report and the page publish both: the suite's measure, and the recall,
false positive rate and predictive equality on months 6 and 7 at the threshold fixed on
month 5. The recall gate uses the fixed threshold, and a gate watches how far the
realised false positive rate drifts from its target.

## 2026-09-27: Challenge (attrition): a twelve month outcome is only known twelve months later

**Raised:** The first split trained on every month end up to December 2024 and tested
on the summer of 2025. A December 2024 label says whether the customer left by December
2025, which the bank could not have known when it scored the summer of 2025.

**Response:** A random or plain temporal split lets training labels come from the
future of the test months whenever the outcome window is longer than the gap. The
model a bank could actually have fitted on 31 May 2025 only had month ends whose windows
had closed by then.

**Changed:** Training uses month ends September 2023 to February 2024, validation March
to May 2024, and test June to August 2025, so every training and validation outcome was
known before the first test month end. The gap is stated in the report beside the split.

## 2026-09-27: Challenge (attrition): the most likely leaver is not the one worth a call

**Raised:** Sorted by probability alone, the top of the retention list fills with new
customers holding a few hundred dollars. A retention call costs the same whoever answers.

**Response:** The list exists to protect deposits. What the bank stands to lose is the
probability times the balances the customer holds, and the two orderings put different
people at the top.

**Changed:** The list is ranked by expected balance at risk. The report publishes, for
the top tenth of the test months, the share of closers and the share of their balances
found by each ordering, so the trade between the two is visible.

## 2026-09-27: The attrition model memorised customers, and the simpler model won

The first attrition fit reached an AUROC of 0.88 on its training months, 0.72 on
validation and 0.55 on test, and never stopped early. The same customers sit in every
month end with the same income and tenure path, so a validation sample of later month
ends was a sample of people the trees had already memorised. Early stopping now uses
customers held out of the fit, the leaves are kept large, and the logistic regression
fitted beside it is a candidate rather than only a benchmark. On held out customers the
boosted model did not beat it by the stated margin, so the logistic regression is the
model and LightGBM is the benchmark.

## 2026-09-27: Reversal: the attrition gate is measured against the ceiling, not a fixed floor

The first gate asked for a test AUROC of 0.70, a number carried over from the fraud
models without asking what this outcome allows. The generator's own monthly hazards,
used as a score with perfect knowledge of the year ahead, reach under 0.6: most attrition
here is chance. A fixed floor above the ceiling can only fail, whatever the model does,
so the gate now asks for half of the separation the ceiling reaches. The change was
made after the first fit failed the old gate, and it is recorded here for that reason.

## 2026-09-27: Challenge (cure): the bucket already tells a collector most of this

**Raised:** A loan thirty days past due cures far more often than one ninety days past
due. A model that only learned the bucket would beat the base rate comfortably and add
nothing a collections supervisor does not already do by working the thirty day list
first.

**Response:** The base rate is the wrong benchmark for this model. The benchmark is the
rule in use: each bucket's cure rate from the training months, applied as a score.

**Changed:** The bucket rule is a benchmark in the report, and a critical gate requires
the model's test AUROC to beat the rule's by two hundredths. Cure rates by bucket are
published beside the model's so the rule's strength is visible.

## 2026-09-27: Challenge (cure): the same delinquent loan sits on both sides of the split

**Raised:** A loan that is past due in June and July 2025 appears in the last training
month and the first validation month, with nearly the same features and the same
outcome. Early stopping and the choice between the two candidates were being made on
loans the fit had already seen.

**Response:** The attrition model memorised customers for the same reason. Month ends
are not independent draws when the unit is a loan that stays delinquent for months.

**Changed:** One loan in five is held out of the fit by a hash of its identifier, and
early stopping and the choice of champion use only held out loans in the validation
months. The test months begin three months after validation ends, so every outcome used
to fit or choose the model was known before the first test month end, and a check in
the trainer refuses to run otherwise.

## 2026-09-27: Challenge (relief): the rate of monetary relief tripled across the window

**Raised:** Complaints received in late 2024 ended in monetary relief about one time in
seventy; by mid 2026 it was closer to one in fourteen. A model fitted on the early
months will score the later ones too low, and a probability threshold chosen on 2025
would flag almost nothing in 2026.

**Response:** The ranking survives a shift in the base rate far better than the
probabilities do. The operating point is a capacity, not a probability: a review team
that can read one complaint in twenty.

**Changed:** The operating point flags the top twentieth of scores, set on the
validation months immediately before the test months. Reliability on the test months is
published with the drift stated beside it, the calibration gate is non critical, and
the monitoring plan resets the operating point when the monthly base rate moves by half.

## 2026-09-27: Challenge (relief): a narrative can name a protected basis

**Raised:** Consumers write about their age, their disability, their military service
and their family. A text model can learn that an elderly widow is more likely to get a
refund, which is a protected basis entering a routing decision by the back door. The
Bureau's own tags mark older Americans and servicemembers.

**Response:** Routing is not a credit decision, but it decides whose complaint a person
reads first, and the same reasoning that keeps age out of a scorecard applies.

**Changed:** `rules/proxies.yaml` now lists words a text model may not learn from, and
the relief model drops them, and any phrase containing them, from its vocabulary. The
Bureau's tags are never features; they are used only to audit flag rates by group, and
a gate watches the ratio.

## 2026-09-27: A third of the complaint narratives are form letters

The first topic model over the narratives found topics made of legal boilerplate:
"section, consumer, usc, agency, furnish", "presume, doctrine, estoppel, silence". They
were form letters, many from credit repair services, filed word for word by different
consumers, and counted as they were they became topics of their own and drowned out
what individual consumers wrote. Grouping narratives by their normalised opening words,
31 percent open like at least four others. Topics are now fitted with each opening
counted once and then scored over every narrative, and each topic reports its share of
form letters. With that change all four themes a reader expects in bank complaints
emerged as topics; before it, two did.

## 2026-09-27: The rederive after the release found five things a green CI could not

Run after v0.1.0 was pushed, `make rederive` stopped at its third stage. Fixing that let it
reach the end, where it reported results that had moved with nothing changed.

- `make warehouse` called dbt from the warehouse folder, which bakes the relative default
  path to the staged tables into every staging view, so reconciliation, run from the
  repository root, found no files. Every earlier build had gone through `ledger warehouse`,
  which passes absolute paths, so the Makefile target had never actually been run. It now
  calls the CLI, and a test holds it there.
- The warehouse fixtures in the test suite built small warehouses in temporary folders but
  let dbt write its run record into the real `warehouse/target`, which is where the controls
  function reads the model and test counts it publishes. A test build now keeps its record
  beside its own database, and the function refuses a record from a partial build.
- The proxy audit listed five models. Function 3 was last run before the attrition, cure and
  relief models existed, and the claim gate cannot see that: it checks documents against the
  manifest, not the manifest against the models on disk. Rerun, it lists eight, none using a
  protected attribute or a proxy.
- The known parameter recovery fits its hazard model on a seeded sample of loan months, but
  the months came from the warehouse in no fixed order, so the same seed drew a different
  sample on each run: the latent risk coefficient read 0.913 in the release and 0.955 on the
  next run. The months are now sorted before sampling. The estimates are 0.940, 0.305 and
  0.470 against stated values of 0.95, 0.30 and 0.45, all inside tolerance as before, and the
  simplified CECL illustration, which uses the macro estimate, moved from $19,055,866 to
  $19,170,851.
- Louvain's communities depend on the order edges are added in as well as on its seed. The
  published communities did not change, but the transfer graph is now built in a fixed order
  so that they cannot.

Floats that DuckDB and Polars sum in parallel also moved in their last bits between runs. The
rederive now compares data files by content, allowing one part in a billion, and still
requires every document to match byte for byte.
