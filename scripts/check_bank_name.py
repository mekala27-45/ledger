"""Verify the fictional bank's name belongs to no FDIC insured institution, past or present.

Checks the full FDIC institution directory (27,834 institutions when fetched,
active and inactive). The directory's names are committed as a compressed
reference file so CI re-verifies without network access; `make fetch` refreshes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REFERENCE = Path("data/reference/fdic_institution_names.csv.gz")
from ledger_scan.bank_name import GENERIC, collisions, distinctive, load_names, normalise  # noqa: F401


def check(root: Path, bank_name: str | None = None, names: list[str] | None = None) -> int:
    if bank_name is None:
        from ledger_core.config import load_config

        bank_name = load_config(root / "config" / "ledger.yaml").bank.name
    directory = names if names is not None else load_names(root / REFERENCE)
    if not directory:
        raise ValueError("the bank name check was given an empty institution directory")
    hits = collisions(bank_name, directory)
    if hits:
        raise ValueError(f"{bank_name!r} collides with insured institutions: {hits[:10]}")
    return len(directory)


if __name__ == "__main__":
    count = check(Path(__file__).resolve().parents[1])
    print(f"bank name check: no match among {count:,} FDIC institutions")
