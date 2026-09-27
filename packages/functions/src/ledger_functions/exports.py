"""The credit and treasury workbook, and flat extracts for a BI tool.

The workbook is for the people who will not open a notebook: expected loss by score
band and the rate shock repricing table carry live Excel formulas, so a reader can
change a PD or a beta and watch the result move, and every sheet says where its
numbers came from. The extracts are the same results as plain CSV for Power BI or any
other tool. Both are written from the committed results, never from the warehouse,
so they match the published figures exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from ledger_core.manifest import Manifest
from ledger_core.paths import Paths
from ledger_core.statements import DEMONSTRATION, NOT_A_DECISION
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

WORKBOOK = "ledger_credit_and_treasury.xlsx"
EXTRACTS = {
    "f02/expected_loss.parquet": "expected_loss.csv",
    "f02/vintages.parquet": "vintages.csv",
    "f06/deposits_monthly.parquet": "deposits_monthly.csv",
    "f08/nii_positions.parquet": "nii_positions.csv",
    "f08/stress_paths.parquet": "stress_paths.csv",
    "f09/backtest.parquet": "chargeoff_backtest.csv",
    "f09/recoveries.parquet": "recoveries.csv",
}


def _header(ws: object, row: list[str]) -> None:
    ws.append(row)  # type: ignore[attr-defined]
    for cell in ws[ws.max_row]:  # type: ignore[attr-defined,index]
        cell.font = Font(bold=True)


def _widths(ws: object) -> None:
    for i, column in enumerate(ws.columns, start=1):  # type: ignore[attr-defined]
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in column)
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, longest + 2))  # type: ignore[attr-defined]


def build_workbook(p: Paths, out: Path) -> dict[str, int]:
    m = Manifest.load(p.results / "manifest.json")
    wb = Workbook()
    readme = wb.active
    assert readme is not None
    readme.title = "Read me"
    for line in (
        "ledger: the credit and treasury workbook",
        DEMONSTRATION,
        NOT_A_DECISION,
        f"Data as of {m.as_of}, seed {m.seed}. Every figure is read from results/manifest.json and the committed results.",
        "Expected loss and Rate shocks carry live formulas: change an input in a shaded column and the result moves.",
    ):
        readme.append([line])
    readme.column_dimensions["A"].width = 120
    counts: dict[str, int] = {}

    # Expected loss: EL = PD x LGD x EAD, as formulas.
    el = pl.read_parquet(p.results / "f02" / "expected_loss.parquet").with_columns(
        pl.col("ead").cast(pl.Float64)
    )
    lgd = float(m.raw("f02.lgd_installment"))  # type: ignore[arg-type]
    ws = wb.create_sheet("Expected loss")
    # Expected loss is summed loan by loan, so the band's PD here is the exposure weighted one
    # that reproduces it: a reader who changes it moves the band's loss exactly as the pipeline would.
    _header(
        ws,
        [
            "Score band",
            "Loans",
            "Exposure at default",
            "PD, exposure weighted, with overlay",
            "LGD",
            "Expected loss",
            "EL rate",
        ],
    )
    for i, row in enumerate(el.iter_rows(named=True), start=2):
        pd_weighted = row["el"] / (lgd * row["ead"]) if row["ead"] else 0.0
        ws.append(
            [row["band"], row["loans"], row["ead"], pd_weighted, lgd, f"=D{i}*E{i}*C{i}", f"=F{i}/C{i}"]
        )
    last = el.height + 1
    ws.append(
        [
            "Total",
            f"=SUM(B2:B{last})",
            f"=SUM(C2:C{last})",
            None,
            None,
            f"=SUM(F2:F{last})",
            f"=F{last + 1}/C{last + 1}",
        ]
    )
    for r in ws.iter_rows(min_row=2):
        r[2].number_format = "$#,##0"
        r[3].number_format = "0.00%"
        r[4].number_format = "0.0%"
        r[5].number_format = "$#,##0"
        r[6].number_format = "0.00%"
    ws.append([])
    ws.append(
        [
            f"Source: {m.label('f02.el_table') if 'f02.el_table' in m.tables else 'results/f02/expected_loss.parquet'}"
        ]
    )
    _widths(ws)
    counts["Expected loss"] = el.height

    # Rate shocks: change = balance x weight x beta x shock / 100, signed by side.
    pos = pl.read_parquet(p.results / "f08" / "nii_positions.parquet")
    ws = wb.create_sheet("Rate shocks")
    ws.append(["Shock, basis points", 200])
    ws["A1"].font = Font(bold=True)
    _header(ws, ["Position", "Side", "Balance", "Repricing weight", "Beta", "Change in NII at the shock"])
    for i, row in enumerate(pos.iter_rows(named=True), start=3):
        sign = "" if row["side"] == "asset" else "-"
        ws.append(
            [
                row["position"],
                row["side"],
                row["balance"],
                row["weight"],
                row["beta"],
                f"={sign}C{i}*D{i}*E{i}*$B$1/10000",
            ]
        )
    last = pos.height + 2
    ws.append(["Total", None, None, None, None, f"=SUM(F3:F{last})"])
    for r in ws.iter_rows(min_row=3):
        r[2].number_format = "$#,##0"
        r[3].number_format = "0.0%"
        r[4].number_format = "0.00"
        r[5].number_format = "$#,##0"
    ws.append([])
    ws.append(["A rise, before any floor. The published table applies each deposit's floor to a fall."])
    _widths(ws)
    counts["Rate shocks"] = pos.height

    # Tables copied as values: scenarios, the model inventory, deposit betas.
    for sheet, key in (
        ("Stress scenarios", "f08.scenario_table"),
        ("Deposit betas", "f06.betas"),
        ("Model inventory", "f10.inventory"),
        ("Charge off backtest", "f09.backtest_table"),
    ):
        if key not in m.tables:
            continue
        table = m.tables[key]
        ws = wb.create_sheet(sheet)
        _header(ws, list(table.columns))
        for cells in table.rows:
            ws.append([json.dumps(v) if isinstance(v, (list, dict)) else v for v in cells])
        ws.append([])
        ws.append([f"Source: {m.label(key)}"])
        _widths(ws)
        counts[sheet] = len(table.rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return counts


def write_extracts(p: Paths, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for source, name in EXTRACTS.items():
        path = p.results / source
        if not path.exists():
            continue
        frame = pl.read_parquet(path)
        frame = frame.with_columns(
            [pl.col(c).cast(pl.Float64) for c, t in frame.schema.items() if isinstance(t, pl.Decimal)]
        )
        target = folder / name
        frame.write_csv(target)
        written.append(target)
    return written


def main(p: Paths) -> dict[str, object]:
    exports = p.results / "exports"
    counts = build_workbook(p, exports / WORKBOOK)
    extracts = write_extracts(p, exports / "extracts")
    return {
        "workbook": str((exports / WORKBOOK).relative_to(p.root)),
        "sheets": counts,
        "extracts": len(extracts),
    }
