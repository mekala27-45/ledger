"""The workbook's formulas compute what the pipeline computed.

Without a spreadsheet engine, the test checks every formula refers to the right
cells. With LibreOffice installed it recalculates the workbook headlessly and checks
the values against the published figures. The skip says which it could not do.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from ledger_core.manifest import Manifest
from ledger_core.paths import Paths
from ledger_functions.exports import build_workbook
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")


@pytest.fixture(scope="module")
def workbook(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wb") / "book.xlsx"
    counts = build_workbook(Paths(ROOT), out)
    assert counts["Expected loss"] > 0 and counts["Rate shocks"] > 0
    return out


def test_every_formula_points_at_its_own_row(workbook: Path) -> None:
    wb = load_workbook(workbook)
    el = wb["Expected loss"]
    for row in range(2, el.max_row):
        f = el.cell(row=row, column=6).value
        if isinstance(f, str) and f.startswith("=D"):
            assert f == f"=D{row}*E{row}*C{row}"
    shocks = wb["Rate shocks"]
    for row in range(3, shocks.max_row):
        f = shocks.cell(row=row, column=6).value
        if isinstance(f, str) and "$B$1" in f:
            assert f.endswith(f"C{row}*D{row}*E{row}*$B$1/10000")
            side = shocks.cell(row=row, column=2).value
            assert f.startswith("=-") == (side == "liability")
    readme = " ".join(str(c.value) for c in wb["Read me"]["A"])
    assert "fictional" in readme and "investment advice" in readme


@pytest.mark.skipif(
    SOFFICE is None, reason="LibreOffice is not installed, so the formulas cannot be recalculated"
)
def test_recalculated_values_match_the_published_figures(workbook: Path, tmp_path: Path) -> None:
    subprocess.run(
        [
            str(SOFFICE),
            "--headless",
            "--calc",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(tmp_path),
            str(workbook),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    values = load_workbook(tmp_path / workbook.name, data_only=True)
    manifest = Manifest.load(ROOT / "results" / "manifest.json")
    el = values["Expected loss"]
    total = [r for r in el.iter_rows(values_only=True) if r[0] == "Total"][0]
    published = float(manifest.raw("f02.el_total"))  # type: ignore[arg-type]
    assert total[5] == pytest.approx(published, rel=1e-6)
    shocks = values["Rate shocks"]
    change = [r for r in shocks.iter_rows(values_only=True) if r[0] == "Total"][0][5]
    assert change == pytest.approx(float(manifest.raw("f08.nii_up200")), abs=1.0)  # type: ignore[arg-type]
