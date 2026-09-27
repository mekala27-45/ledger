"""The planted identifier scan over tables: clean pass, planted identifiers found, refusal on nothing."""

from __future__ import annotations

import polars as pl
import pytest
from ledger_scan.tables import scan_frame, scan_text

NAMES = {"jordan whitfield", "maria okonkwo"}
# A Luhn valid test number from a card network's published test ranges.
PAN = "4111111111111111"


def test_clean_table_passes() -> None:
    frame = pl.DataFrame(
        {"card_key": ["Kab12cd34ef"], "category": ["grocery_pos"], "note": ["paid at the counter"]}
    )
    assert scan_frame(frame, "t", NAMES) == []


def test_planted_card_number_ssn_and_name_are_found() -> None:
    frame = pl.DataFrame(
        {
            "memo": [f"card {PAN} on file", "ssn 123-45-6789 given", "ok"],
            "holder": ["Jordan Whitfield", "someone", "x"],
            "narrative": ["the teller said maria okonkwo would call back about the dispute", "a", "b"],
        }
    )
    kinds = sorted(f.kind for f in scan_frame(frame, "t", NAMES))
    assert kinds == ["card_number", "generated_person_name", "generated_person_name", "ssn"]


def test_findings_never_echo_the_identifier() -> None:
    frame = pl.DataFrame({"memo": [f"card {PAN}"]})
    (finding,) = scan_frame(frame, "t", NAMES)
    assert PAN not in finding.sample


def test_name_matching_can_be_switched_off_for_regulator_text() -> None:
    frame = pl.DataFrame({"narrative": ["jordan whitfield wrote to the bank about fees twice last month"]})
    assert scan_frame(frame, "cfpb", NAMES, names_apply=False) == []


def test_scan_refuses_nothing() -> None:
    with pytest.raises(ValueError, match="empty"):
        scan_frame(pl.DataFrame(), "t", NAMES)


def test_luhn_invalid_digit_runs_are_not_card_numbers() -> None:
    assert scan_text("reference 4111111111111112 and phone 973 555 0100", set()) == []
