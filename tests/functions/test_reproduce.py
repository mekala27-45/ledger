"""The rederive comparison: documents exactly, data by content with float noise allowed.

Each rule is tested three ways: it passes what it should, it catches the change it exists
to catch, and it does not wave through a file it cannot read as data.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import polars as pl
import pytest
from ledger_functions.reproduce import TOLERANCE, frames_close, reproduced, values_close
from openpyxl import Workbook


def _parquet(frame: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    frame.write_parquet(buf)
    return buf.getvalue()


BASE = pl.DataFrame({"band": ["A", "B"], "loans": [10, 20], "el": [1_234_567.891, 0.0], "pd": [0.02, None]})


def test_float_noise_in_the_last_bits_is_reproduced() -> None:
    noisy = BASE.with_columns(el=pl.col("el") * (1 + 3e-16), pd=pl.col("pd") + 2e-17)
    assert frames_close(BASE, noisy)
    assert values_close(
        {"el": 1_234_567.891, "rows": [0.1, 2]}, {"el": 1_234_567.891000001, "rows": [0.1, 2]}
    )


@pytest.mark.parametrize(
    "changed",
    [
        BASE.with_columns(el=pl.col("el") * (1 + 1e-6)),  # a real move, far above noise
        BASE.with_columns(loans=pl.Series([10, 21])),  # an integer is exact
        BASE.with_columns(band=pl.Series(["A", "C"])),  # so is text
        BASE.with_columns(pd=pl.Series([0.02, 0.03])),  # a null became a number
        BASE.head(1),  # a row went missing
        BASE.reverse(),  # rows reordered: a table's order is part of what it says
    ],
)
def test_a_real_change_is_caught(changed: pl.DataFrame) -> None:
    assert not frames_close(BASE, changed)


def test_numbers_in_json_are_compared_like_frames() -> None:
    assert not values_close({"n": 5}, {"n": 6})
    assert not values_close({"x": 0.5}, {"x": 0.5 + 10 * TOLERANCE})
    assert not values_close([1, 2], [1, 2, 3])
    assert not values_close({"a": 1}, {"b": 1})
    assert not values_close(True, 1)
    assert values_close(float("nan"), float("nan"))


def test_files_are_judged_by_their_kind(tmp_path: Path) -> None:
    committed = _parquet(BASE)
    path = tmp_path / "expected_loss.parquet"
    path.write_bytes(_parquet(BASE.with_columns(el=pl.col("el") * (1 + 2e-16))))
    assert reproduced(path, committed)
    path.write_bytes(_parquet(BASE.with_columns(el=pl.col("el") * 1.01)))
    assert not reproduced(path, committed)

    doc = tmp_path / "RESULTS.md"
    doc.write_text("Expected loss $8,409,265\n", encoding="utf-8")
    assert reproduced(doc, doc.read_bytes())
    assert not reproduced(doc, b"Expected loss $8,409,266\n")  # a document must match exactly

    data = tmp_path / "network.json"
    data.write_text(json.dumps({"amount": 0.30000000000000004}), encoding="utf-8")
    assert reproduced(data, json.dumps({"amount": 0.3}).encode())


def test_a_workbook_is_compared_by_its_cells_not_its_timestamps(tmp_path: Path) -> None:
    def book(el: float) -> bytes:
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(["Band", "EL"])
        ws.append(["A", el])
        ws.append(["Total", "=SUM(B2:B2)"])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    path = tmp_path / "book.xlsx"
    path.write_bytes(book(100.0 * (1 + 1e-15)))
    assert reproduced(path, book(100.0))
    path.write_bytes(book(101.0))
    assert not reproduced(path, book(100.0))
