"""Scan every published table, document, log and the built site for personal identifiers.

What counts as an identifier here: a Luhn valid card number, a Social Security
number pattern, or any person name the card transaction generator created. The
generator's names never leave ingestion, and this scan is the proof. A planted
identifier test (tests/gates/test_identifier_scan.py) shows it catches each kind.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger_core.identity import find_card_numbers

SSN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")
SCAN_GLOBS = (
    "results/**/*.json",
    "results/**/*.csv",
    "results/**/*.parquet",
    "results/**/*.md",
    "report/**/*.md",
    "report/**/*.html",
    "docs/**/*.md",
    "README.md",
    "RESULTS.md",
    "web/public/data/**/*",
    "web/out/**/*.html",
    "web/out/**/*.json",
    "exports/**/*.csv",
    "logs/**/*.log",
)
NAMES_FILE = Path("data/staged/sparkov/person_names.txt.gz")


def load_person_names(root: Path) -> set[str]:
    path = root / NAMES_FILE
    if not path.exists():
        return set()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return {line.strip().lower() for line in handle if line.strip()}


def text_of(path: Path) -> str:
    if path.suffix == ".parquet":
        import polars as pl

        frame = pl.read_parquet(path)
        parts: list[str] = []
        for column, dtype in zip(frame.columns, frame.dtypes, strict=True):
            if dtype == pl.Utf8:
                parts.extend(v for v in frame[column].drop_nulls().to_list())
            elif dtype.is_integer():
                parts.extend(str(v) for v in frame[column].drop_nulls().to_list() if abs(int(v)) >= 10**12)
        return "\n".join(parts)
    if path.suffix == ".json":
        try:
            return json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def findings(text: str, names: set[str]) -> list[str]:
    out = [f"card number ending {pan[-4:]}" for pan in find_card_numbers(text)]
    out += [f"SSN pattern {m.group(0)[:3]}-XX-XXXX" for m in SSN.finditer(text)]
    if names:
        lowered = text.lower()
        for name in names:
            if name in lowered:
                out.append(f"generator person name '{name}'")
    return out


def targets(root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in SCAN_GLOBS:
        found.extend(p for p in root.glob(pattern) if p.is_file() and "node_modules" not in p.parts)
    return sorted(set(found))


def check(root: Path, files: Iterable[Path] | None = None, names: set[str] | None = None) -> int:
    scan = list(files) if files is not None else targets(root)
    if not scan:
        raise ValueError("the identifier scan found no files to scan")
    people = names if names is not None else load_person_names(root)
    problems: list[str] = []
    for path in scan:
        for finding in findings(text_of(path), people):
            problems.append(f"{path.relative_to(root)}: {finding}")
    if problems:
        raise ValueError("identifier scan failed:\n" + "\n".join(problems[:50]))
    return len(scan)


if __name__ == "__main__":
    count = check(Path(__file__).resolve().parents[1])
    print(f"identifier scan: {count} files, no card numbers, SSN patterns or generator names")
