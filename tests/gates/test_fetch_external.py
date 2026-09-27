"""The external data check: matching files pass, a changed file fails, missing files are reported."""

from __future__ import annotations

from pathlib import Path

from scripts import fetch_external as fx


def _plant(root: Path, item: fx.Expected, body: bytes) -> None:
    path = root / "data" / "external" / item.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def test_nothing_present_is_all_missing(tmp_path: Path) -> None:
    present, missing, changed = fx.check(tmp_path)
    assert present == [] and changed == []
    assert len(missing) == len(fx.EXPECTED)


def test_a_file_with_a_different_hash_is_changed(tmp_path: Path) -> None:
    _plant(tmp_path, fx.EXPECTED[0], b"not the published file")
    _, _, changed = fx.check(tmp_path)
    assert changed == [fx.EXPECTED[0].path]


def test_a_matching_file_is_present(tmp_path: Path, monkeypatch: object) -> None:
    body = b"published bytes"
    item = fx.Expected("macro/x.csv", fx.hashlib.sha256(body).hexdigest()[:16], "how")
    _plant(tmp_path, item, body)
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setattr(fx, "EXPECTED", (item,))
    try:
        present, missing, changed = fx.check(tmp_path)
    finally:
        mp.undo()
    assert present == ["macro/x.csv"] and missing == [] and changed == []
