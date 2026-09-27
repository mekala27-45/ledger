"""The planted identifier scan over tables.

Three kinds of identifier must never appear in a staged table, a mart, a result
or the built site: a card number (Luhn valid, 13 to 19 digits), a social
security number pattern, and the full name of any person the card generator
invented. The generator's names are kept only in data/staged/sparkov for this
scan. Free text published by a regulator (CFPB narratives) is scanned for card
and SSN patterns only, because a common first and last name pair appearing in
a real consumer's narrative is not a generated identity.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from ledger_core.identity import find_card_numbers

SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")


@dataclass(frozen=True)
class Finding:
    table: str
    column: str
    kind: str
    sample: str


def load_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return {line.strip() for line in handle if line.strip()}


def _mask(value: str) -> str:
    return value[:2] + "*" * max(0, len(value) - 4) + value[-2:] if len(value) > 4 else "****"


def scan_text(text: str, names: set[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = [("card_number", _mask(pan)) for pan in find_card_numbers(text)]
    found += [("ssn", _mask(m.group(0))) for m in SSN.finditer(text)]
    if names:
        tokens = re.findall(r"[a-z][a-z'\-]+", text.lower())
        for a, b in zip(tokens, tokens[1:], strict=False):
            if f"{a} {b}" in names:
                found.append(("generated_person_name", f"{a[0]}. {b[0]}."))
    return found


def scan_frame(
    frame: pl.DataFrame, table: str, names: set[str], *, names_apply: bool = True
) -> list[Finding]:
    """Scan every string column. Refuses a frame with no string columns and no rows."""
    if frame.height == 0 and frame.width == 0:
        raise ValueError(f"refusing to scan an empty table {table}")
    findings: list[Finding] = []
    for column, dtype in frame.schema.items():
        if dtype not in (pl.Utf8, pl.Categorical) and not isinstance(dtype, pl.Enum):
            continue
        values = frame.get_column(column).cast(pl.Utf8).drop_nulls().unique()
        # Cheap prefilter: only strings with a digit run or two letter words can hold an identifier.
        digits = values.filter(values.str.contains(r"\d{3}"))
        for value in digits.to_list():
            for kind, sample in scan_text(value, set()):
                findings.append(Finding(table, column, kind, sample))
        if names and names_apply:
            lowered = values.str.to_lowercase()
            exact = lowered.filter(lowered.is_in(list(names)))
            for value in exact.to_list():
                findings.append(Finding(table, column, "generated_person_name", _mask(value)))
            long_text = lowered.filter(lowered.str.len_chars() > 40)
            for value in long_text.to_list():
                for kind, sample in scan_text(value, names):
                    if kind == "generated_person_name":
                        findings.append(Finding(table, column, kind, sample))
    return findings
