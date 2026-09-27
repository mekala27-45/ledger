"""Verify the fictional bank's name belongs to no FDIC insured institution, past or present.

Checks the full FDIC institution directory (27,834 institutions when fetched,
active and inactive). The directory's names are committed as a compressed
reference file so CI re-verifies without network access; `make fetch` refreshes it.
"""

from __future__ import annotations

import csv
import difflib
import gzip
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REFERENCE = Path("data/reference/fdic_institution_names.csv.gz")
GENERIC = {
    "bank",
    "banks",
    "the",
    "of",
    "and",
    "trust",
    "company",
    "co",
    "national",
    "association",
    "na",
    "savings",
    "fsb",
    "ssb",
    "state",
    "federal",
    "bancorp",
    "financial",
    "community",
    "loan",
    "sla",
    "inc",
    "corporation",
    "corp",
    "&",
}


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", name.lower()).strip()


def distinctive(name: str) -> str:
    return " ".join(t for t in normalise(name).split() if t not in GENERIC)


def load_names(path: Path) -> list[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row["NAME"] for row in reader if row.get("NAME")]


def collisions(bank_name: str, names: list[str], cutoff: float = 0.88) -> list[str]:
    target = distinctive(bank_name)
    squashed = target.replace(" ", "")
    hits: list[str] = []
    for name in names:
        other = distinctive(name)
        if not other:
            continue
        if other == target or other.replace(" ", "") == squashed:
            hits.append(name)
            continue
        if squashed and squashed in other.replace(" ", ""):
            hits.append(name)
            continue
        if difflib.SequenceMatcher(None, squashed, other.replace(" ", "")).ratio() >= cutoff:
            hits.append(name)
    return hits


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
