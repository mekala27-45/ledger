from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_bank_name

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ["The Harbor Bank of Maryland", "HarborOne Bank", "Peapack Private Bank & Trust", "Lakeland Bank"]


def test_fictional_name_passes_a_directory_without_it() -> None:
    assert check_bank_name.check(ROOT, "Harborline Bank", DIRECTORY) == len(DIRECTORY)


@pytest.mark.parametrize(
    "planted",
    ["Harborline Bank", "HARBORLINE BANK, N.A.", "Harbor Line Savings Bank", "The Harborline Trust Company"],
)
def test_a_planted_institution_is_caught(planted: str) -> None:
    with pytest.raises(ValueError, match="collides"):
        check_bank_name.check(ROOT, "Harborline Bank", [*DIRECTORY, planted])


def test_refuses_to_pass_on_an_empty_directory() -> None:
    with pytest.raises(ValueError, match="empty institution directory"):
        check_bank_name.check(ROOT, "Harborline Bank", [])


def test_distinctive_tokens_drop_generic_words() -> None:
    assert check_bank_name.distinctive("The Harborline Bank, National Association") == "harborline"


@pytest.mark.skipif(
    not (ROOT / check_bank_name.REFERENCE).exists(), reason="FDIC reference names not fetched yet"
)
def test_against_the_full_fdic_directory() -> None:
    assert check_bank_name.check(ROOT) > 20_000
