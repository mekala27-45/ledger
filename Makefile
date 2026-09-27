# The pipeline in the order it runs. dags/ledger.py mirrors this order, and
# tests/pipeline/test_dag_order.py fails if the two disagree.

PY := uv run python
LEDGER := uv run ledger

.PHONY: help setup fetch generate sparkov ingest contracts warehouse reconcile metrics models functions manifest render export site-data pipeline gates lint types test check rederive web demo clean

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | tr '\n' ' '; echo

setup:
	uv sync
	npm --prefix web ci

fetch:
	$(PY) scripts/fetch_external.py

generate:
	$(LEDGER) generate

sparkov:
	$(PY) scripts/run_sparkov.py

ingest:
	$(LEDGER) ingest

contracts:
	$(LEDGER) contracts

# Through the CLI, which hands dbt absolute paths to the staged tables. Called bare from the
# warehouse folder, dbt bakes the relative default into every staging view, and the views
# break for anything that opens the database from the repository root.
warehouse:
	$(LEDGER) warehouse

reconcile:
	$(LEDGER) reconcile

metrics:
	$(LEDGER) metrics

models:
	$(LEDGER) models

functions:
	$(LEDGER) functions

manifest:
	$(LEDGER) manifest

render:
	$(PY) scripts/check_published_numbers.py --write

export:
	$(LEDGER) export

site-data:
	$(LEDGER) site-data

pipeline: generate ingest contracts warehouse reconcile metrics models functions manifest render export site-data

gates:
	$(PY) scripts/check_no_em_dash.py
	$(PY) scripts/check_vocabulary.py
	$(PY) scripts/check_statements.py
	$(PY) scripts/check_published_numbers.py
	$(PY) scripts/check_bank_name.py
	$(PY) scripts/scan_for_planted_identifiers.py
	node scripts/validate_palette.js --config web/src/theme/palette.json

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term-missing:skip-covered

check: lint types gates test

rederive:
	$(PY) scripts/reset_and_rederive.py

web:
	npm --prefix web run build

demo:
	$(PY) scripts/build_demo_gif.py

clean:
	rm -rf warehouse/target warehouse/ledger.duckdb data/staged/* data/quarantine/* web/out
