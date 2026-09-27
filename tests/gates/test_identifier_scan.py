from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from scripts import scan_for_planted_identifiers as scan

# A Luhn valid test number in the 4111 range used by card networks for testing.
PLANTED_PAN = "4111 1111 1111 1111"
PLANTED_SSN = "123-45-6789"


def test_clean_documents_pass(tmp_path: Path) -> None:
    doc = tmp_path / "a.md"
    doc.write_text("Customer C0012345 opened account A0098765 on 2024-03-02 for $1,250.00.")
    assert scan.check(tmp_path, [doc], names=set()) == 1


def test_planted_card_number_is_caught(tmp_path: Path) -> None:
    doc = tmp_path / "a.md"
    doc.write_text(f"see {PLANTED_PAN}")
    with pytest.raises(ValueError, match="card number ending 1111"):
        scan.check(tmp_path, [doc], names=set())


def test_planted_ssn_is_caught(tmp_path: Path) -> None:
    doc = tmp_path / "a.json"
    doc.write_text('{"note": "' + PLANTED_SSN + '"}')
    with pytest.raises(ValueError, match="SSN pattern"):
        scan.check(tmp_path, [doc], names=set())


def test_planted_generator_name_is_caught(tmp_path: Path) -> None:
    doc = tmp_path / "a.md"
    doc.write_text("Flagged transaction for Jennifer Banks at a gas station.")
    with pytest.raises(ValueError, match="generator person name"):
        scan.check(tmp_path, [doc], names={"jennifer banks"})


def test_card_number_inside_parquet_integer_column_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "t.parquet"
    pl.DataFrame({"amount": [12.5], "cc": [4111111111111111]}).write_parquet(path)
    with pytest.raises(ValueError, match="card number"):
        scan.check(tmp_path, [path], names=set())


def test_refuses_to_pass_on_nothing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no files"):
        scan.check(tmp_path, [], names=set())
