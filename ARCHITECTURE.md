# Architecture

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

How the pieces fit, in the order data moves through them. Every stage is a `make` target
and a `ledger` subcommand, and `dags/ledger.py` runs the same targets in the same order.

## The flow

```
config/ledger.yaml            every stated assumption, in one file
        |
packages/bankgen  ----------> data/raw/generated, data/raw/truth
scripts/fetch_external.py --> data/external (HMDA, CFPB, FDIC, BAF, UCI, FRB, macro), content hashed
        |
packages/contracts ---------> data/staged, data/quarantine        pandera contracts, quarantine by rule
        |
warehouse (dbt on DuckDB) --> staging, marts, dbt tests            the only place SQL shapes data
        |
ledger reconcile, metrics --> the ledger to the cent (f11), the metric layer at four grains (metrics/bank.yaml)
        |
packages/models ------------> results/models/<id>                  train, gate, document under the contract
        |
packages/functions ---------> results/fNN                           twelve functions over marts and models
        |
ledger manifest ------------> results/manifest.json                 every published value with its provenance
        |
packages/render (claim gate)> README.md, RESULTS.md, docs, report  rendered from the manifest, diffed whole
        |
ledger export --------------> results/exports                       the workbook and the BI extracts
ledger site-data -----------> web/public/data                       the committed bundle the site reads
        |
web (Next.js static export) > GitHub Pages                           works with no API and no key
packages/api (FastAPI) -----> Fly                                    scoring, the desk stream, cases, audit
```

## The packages

| Package | What it owns |
| --- | --- |
| `core` | Paths, the configuration model, the censoring calendar, the point in time frame, the manifest and its formats, the two statements |
| `bankgen` | The seeded generator: customers, deposits, loans, the general ledger, the macro path, injected typologies and defects, and the truth files that let every recovery be checked |
| `contracts` | Schemas for every raw table, quarantine rules, and staging |
| `scorecard` | Weight of evidence binning, information value, points, adverse action reasons, the proxy list reader |
| `models` | The model contract, promotion gates, evaluation, the registry, and the trainers for the credit, application fraud, attrition and cure models |
| `desk` | The card fraud model's point in time features, the rules, the operating point, late labels and the replay |
| `crime` | The typology rules, alert triage, and the transfer network |
| `fairness` | Disparity ratios, Benjamini and Hochberg, the adjusted fair lending model |
| `nlp` | Complaint topics and the relief model |
| `stress` | Repricing gaps under rate shocks and the macro link for the supervisory scenarios |
| `insights` | The rules engine that writes the glance page's sentences from the metric layer |
| `functions` | The twelve function modules, the manifest merge, the site bundle and the exports |
| `render` | The claim gate |
| `scan` | The planted identifier scan and the fictional bank name check |
| `api` | FastAPI: scoring, the scorecard endpoint, the desk's stream, alerts, cases and the audit log, on Postgres |

## Rules that hold everywhere

- **A number is published only through the manifest.** Functions and trainers write values,
  tables and figures with their provenance (backend, population, source, seed, as of date).
  Documents are templates that read the manifest; the claim gate re-renders them and fails
  on any difference, and refuses a template with a number typed into its prose.
- **Every model is under the contract.** Thirteen lines from `trained` to `explainable`, a
  validation report in the order SR 11-7 asks for, promotion gates set before the model is
  evaluated, and at least two effective challenges on record in `DECISIONS.md`. A report
  with a section missing does not render.
- **Time is explicit.** Features use only what was known before the prediction time, and a
  leakage test recomputes sampled rows from raw history. Outcomes are used only once their
  windows have closed, which is why every split leaves a gap the length of its outcome.
- **Protected attributes are measured, never used.** `rules/proxies.yaml` lists them and the
  proxies that stand in for them; every model's feature list is tested against it.
- **Generated and real data are labelled.** Every figure carries its backend, and the page,
  table or report around it says which it is.

## The site

A Next.js static export. Server components read the manifest and the bundle at build time;
client components draw the charts, run the desk's recorded replay, rebin the scorecard, and
query the explore page's tables with DuckDB compiled to WebAssembly over Arrow files. When
the live API is reachable the desk streams from it; when it is not, the page says so and
plays the recording. Playwright checks every route for both statements, every legend,
every table toggle and phone layouts.

## Checks in CI

Lint, types, the tests with the coverage floor, the gates (claim gate, dashes, vocabulary,
statements, bank name, identifier scan, palette), the site's build and browser tests, and
both container images. A version tag reruns the gates and cuts a release.
