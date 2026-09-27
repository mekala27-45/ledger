from __future__ import annotations

from pathlib import Path

import pytest
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest


def _manifest() -> Manifest:
    return Manifest(as_of="2026-08-31", seed=1)


def test_values_round_trip_and_format(tmp_path: Path) -> None:
    m = _manifest()
    m.put(
        "f01.nim", 0.031234, "pct2", backend="generated", population="Harborline Bank", source="mart_ratios"
    )
    m.put_table(
        "f02.card",
        ["bin", "points"],
        ["text", "int"],
        [["< 600", 12], ["600+", 41]],
        backend="generated",
        population="booked loans",
        source="scorecard",
    )
    path = tmp_path / "manifest.json"
    m.save(path)
    loaded = Manifest.load(path)
    assert loaded.text("f01.nim") == "3.12%"
    assert "| < 600 | 12 |" in loaded.table_markdown("f02.card")
    assert loaded.label("f01.nim") == "Source: generated, Harborline Bank, seed 1, as of 2026-08-31."


def test_rewriting_a_key_is_refused() -> None:
    m = _manifest()
    m.put("a.b", 1, "int", backend="static", population="x", source="y")
    with pytest.raises(ValueError, match="twice"):
        m.put("a.b", 2, "int", backend="static", population="x", source="y")


def test_unknown_backend_is_refused() -> None:
    with pytest.raises(ValueError, match="backend"):
        _manifest().put("a.b", 1, "int", backend="spreadsheet", population="x", source="y")


def test_empty_table_is_refused() -> None:
    with pytest.raises(ValueError, match="no rows"):
        _manifest().put_table("a.t", ["x"], ["int"], [], backend="static", population="p", source="s")


def test_saved_manifest_is_deterministic(tmp_path: Path) -> None:
    a, b = _manifest(), _manifest()
    for m in (a, b):
        m.put("z.v", 1 / 3, "float3", backend="static", population="p", source="s")
        m.put("a.v", 2.0, "float1", backend="static", population="p", source="s")
    a.save(tmp_path / "a.json")
    b.save(tmp_path / "b.json")
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


@pytest.mark.parametrize(
    ("value", "fmt", "expected"),
    [
        (1234567, "int", "1,234,567"),
        (0.1234, "pct1", "12.3%"),
        (-0.0512, "spct1", "-5.1%"),
        (0.0512, "spct1", "+5.1%"),
        (1234.5, "usd2", "$1,234.50"),
        (-2500, "usd0", "-$2,500"),
        (12_345_678, "usdm", "$12.3M"),
        (1_234_567_890, "usdb", "$1.23B"),
        (125, "bps", "125 bp"),
        (float("nan"), "pct1", "not available"),
        # Anything that rounds to zero prints unsigned, in every format.
        (-0.0, "int", "0"),
        (-0.0001, "pct1", "0.0%"),
        (-0.0004, "float3", "0.000"),
        (-0.00001, "spct1", "0.0%"),
        (0.00001, "spct1", "0.0%"),
        (-0.0, "usd0", "$0"),
        (-0.4, "usd0", "$0"),
        (-0.6, "usd0", "-$1"),
        (-40_000, "usdm", "$0.0M"),
        (-1_234.5, "usd2", "-$1,234.50"),
    ],
)
def test_formats(value: float, fmt: str, expected: str) -> None:
    assert format_value(value, fmt) == expected
