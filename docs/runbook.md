# Runbook

> Harborline Bank is fictional. This is a demonstration on generated data and public datasets; no real customer, account or transaction of any real institution appears here.
>
> Nothing here is a credit decision, a fraud determination, a suspicious activity finding or investment advice.

What to run, in what order, and what to do when something fails.

## From a fresh clone

```
make setup        # uv sync and the site's npm install
make fetch        # the public datasets, content hashed into data/external (see data/PROVENANCE.md)
make pipeline     # generate, ingest, contracts, warehouse, reconcile, metrics, models,
                  # functions, manifest, render, export, site-data
make check        # lint, types, gates, tests
make web          # build the static site into web/out
```

`make fetch` is the only step that reaches the internet, and it is run by hand. Everything
after it is deterministic for a given seed in `config/ledger.yaml`.

## Before a release

```
make rederive
```

It clears everything derived, runs the pipeline from the contracts on, runs every gate,
and fails if any committed result differs afterwards. Run it after recording the demo or
touching the live API, so the published figures are the ones a fresh clone reproduces.
Then tag: `git tag -a vX.Y.Z -m "..."` and push the tag; the release workflow reruns the
gates and attaches the workbook.

## Deploying

- **The site.** A push to `main` runs `.github/workflows/pages.yml`, which builds the static
  export with the base path `/ledger` and publishes it to GitHub Pages. Repository settings:
  Pages source "GitHub Actions".
- **The API.** `fly deploy` builds `Dockerfile.api` (see `fly.toml`). It needs a Postgres
  database in `DATABASE_URL`, runs its migrations on start, and serves the desk's stream.
  Set the repository variable `LEDGER_API_URL` to its address and rebuild the site; until
  then the desk plays its recording and says so.

## When a gate fails

| Gate | What it means | What to do |
| --- | --- | --- |
| Claim gate | A document and the manifest disagree, or a template has a number typed into its prose | Rerun `make manifest render`; if a template has a typed number, read it from the manifest instead |
| Statements | A page, report or response lost one of the two statements | Restore it from `ledger_core.statements`; never retype it |
| Dashes, vocabulary | An em or en dash, or a phrase on the filler list | Rewrite the sentence |
| Identifier scan | Something that looks like a card number, an SSN, or the generator's name in a published file | Find what wrote it; mask it at the source |
| Bank name | The fictional bank's name matches a real FDIC institution | Choose another name in `config/ledger.yaml` |
| Coverage | The tests cover under the floor | Add a test that runs the new code, not an exclusion |

## When a model fails its gates

A critical gate failure means the model is not approved and stays in development; its
integration falls back to the stated alternative (the metadata model for relief, the
bucket rule for cure). Do not move a gate after seeing a result. If a gate was set wrong,
record the reversal in `DECISIONS.md` with the reason and the fact that it came after the
result, as the attrition entry does.
