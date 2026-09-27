"""The rederive's comparison, on a small repository of its own.

A data file that moved only by float noise is put back to its committed bytes; a
document that changed by one character, a data file that really moved, and an output
nobody committed are all reported.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest

from scripts import reset_and_rederive as rr

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _parquet(path: Path, el: float) -> None:
    buf = io.BytesIO()
    pl.DataFrame({"band": ["A"], "el": [el]}).write_parquet(buf)
    path.write_bytes(buf.getvalue())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "results" / "f02").mkdir(parents=True)
    _parquet(tmp_path / "results" / "f02" / "expected_loss.parquet", 8_409_265.25)
    _parquet(tmp_path / "results" / "f02" / "vintages.parquet", 0.125)
    (tmp_path / "RESULTS.md").write_text("Expected loss $8,409,265\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "results")
    return tmp_path


def test_noise_is_restored_and_nothing_is_reported(repo: Path) -> None:
    _parquet(repo / "results" / "f02" / "expected_loss.parquet", 8_409_265.25 * (1 + 2e-16))
    moved, noise = rr.compare(repo)
    assert moved == [] and noise == ["results/f02/expected_loss.parquet"]
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True)
    assert status.stdout == ""


def test_real_changes_and_new_outputs_are_reported(repo: Path) -> None:
    _parquet(repo / "results" / "f02" / "vintages.parquet", 0.126)
    (repo / "RESULTS.md").write_text("Expected loss $8,409,266\n", encoding="utf-8")
    _parquet(repo / "results" / "f02" / "new_table.parquet", 1.0)
    moved, noise = rr.compare(repo)
    assert noise == []
    assert sorted(line[3:] for line in moved) == [
        "RESULTS.md",
        "results/f02/new_table.parquet",
        "results/f02/vintages.parquet",
    ]
