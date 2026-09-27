# Contributing

## Setup

```bash
uv sync                      # Python 3.12 workspace, dev and warehouse groups
npm --prefix web ci          # site dependencies
make check                   # lint, types, gates, tests
```

`make fetch` needs network access to the public data hosts listed in
`data/PROVENANCE.md`. Everything else runs offline.

## Rules the gates enforce

- No em or en dashes in authored files (`scripts/check_no_em_dash.py`).
- No filler vocabulary (`scripts/check_vocabulary.py`).
- Both statements on every page, report and API response (`scripts/check_statements.py`,
  `tests/api/test_statements_on_every_endpoint.py`).
- No number typed by hand into a document. Documents are rendered from
  `results/manifest.json` by `scripts/check_published_numbers.py --write`, and CI
  re-renders and diffs every file.
- No card number, SSN pattern or generator person name in anything published
  (`scripts/scan_for_planted_identifiers.py`).
- The bank name stays fictional (`scripts/check_bank_name.py`).

Each gate has three tests: it passes clean input, it fails on the defect it
exists for, and it refuses to report a pass when it was given nothing to check.

## Commits

Conventional commits: `feat(scope):`, `fix(scope):`, `test(scope):`, `docs:`, `ci:`,
`chore:`. One logical change per commit.
