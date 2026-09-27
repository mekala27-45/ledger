"""Whether a bank name collides with any FDIC insured institution, past or present.

Collision means the same distinctive words after generic banking words are removed
(bank, trust, national, savings and the like), one name's distinctive words
contained in the other's, or a close spelling by sequence similarity.
"""

from __future__ import annotations

import csv
import difflib
import gzip
import re
from pathlib import Path

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
