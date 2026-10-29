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
after it is deterministic for a given seed in `config/ledger.yaml`, down to the last bits of
floats that DuckDB and Polars sum in parallel, which can differ from run to run.

## Before a release

```
make rederive
```

It clears everything derived, runs the pipeline from the contracts on, runs every gate,
and fails if any committed result differs afterwards: a document by a single byte, a data
file by more than one part in a billion in any number. Data files that moved less than
that are put back to their committed bytes, and the run says how many. Run it after
recording the demo or touching the live API, so the published figures are the ones a fresh
clone reproduces, and after adding a model, since functions such as the proxy audit read
every model on disk.
Then tag: `git tag -a vX.Y.Z -m "..."` and push the tag; the release workflow reruns the
gates and attaches the workbook.

## Deploying

- **The site.** A push to `main` runs `.github/workflows/pages.yml`, which builds the static
  export with the base path `/ledger` and publishes it to GitHub Pages. Repository settings:
  Pages source "GitHub Actions".
- **The API.** Vercel builds `Dockerfile.vercel` and serves it as a container function on the free
  Hobby plan; the migration runs when an instance starts. Once: run `deploy/new-token.ps1` on the
  machine that will verify the deploy (it writes `deploy/write-token.txt`, ignored by git, and puts
  the token on the clipboard); import the repository in Vercel with the preset Container; set
  `DATABASE_URL` to the Neon connection string on the direct host (not the `-pooler` one),
  `LEDGER_API_TOKEN` to the token and `LEDGER_CORS_ORIGINS` to `https://mekala27-45.github.io`; deploy.
  Then write the address in `deploy/live-url.txt`, run `deploy/verify.ps1` from that machine (it
  writes `results/deploy/verification.json`), and set the repository variable `LEDGER_API_URL` to the
  address so the next Pages build points the desk at it. Until then the desk plays its recording and
  says so. `fly deploy` with `fly.toml` and `Dockerfile.api` is the route for an account with a card.
- **The replay.** The image replays the committed `results/models/fraud_card/replay_stream.parquet`.
  `scripts/build_replay.py --check` rebuilds it, and `replay_history.parquet`, from the staged card
  stream and the committed model, and fails unless the rebuild reproduces the published desk; run it
  after anything that changes the model or the stream, never a retrain for this alone.

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
