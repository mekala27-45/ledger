"""Export the committed bundle the static site reads: JSON for pages, parquet for DuckDB-WASM.

Everything here is derived from results/ and the warehouse. Nothing customer level
leaves: the site gets aggregates, curves, model tables and the recorded replay of
card transactions keyed by masked, salted card keys.
"""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import pyarrow as pa
import pyarrow.ipc
from ledger_core.paths import Paths
from markdown_it import MarkdownIt

EXPLORE_QUERIES = {
    "bank_month": "select * from marts.mart_bank_month order by month",
    "vintage_curves": "select * from marts.mart_vintage_curves order by vintage, months_on_book",
    "roll_rates": "select * from marts.mart_roll_rates order by month, from_bucket, to_bucket",
    "portfolio_monthly": "select * from marts.mart_portfolio_monthly order by product, month",
    "deposits_monthly": "select * from marts.mart_deposits_monthly order by product, month",
    "fdic_peers": "select * from marts.mart_fdic_peer_quarter",
    "gl_account_month": "select * from marts.mart_gl_account_month order by gl_account, month",
    "macro_monthly": "select * from marts.mart_macro_monthly order by month",
    "scenarios": "select * from marts.mart_scenarios order by scenario, quarter",
}


def _records(frame: pl.DataFrame) -> list[dict[str, Any]]:
    out = []
    for row in frame.to_dicts():
        clean = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            elif isinstance(v, Decimal):
                v = float(v)
            elif isinstance(v, float) and v != v:  # NaN
                v = None
            clean[k] = v
        out.append(clean)
    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), default=str) + "\n", encoding="utf-8")


def export(p: Paths, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    out = p.web_data
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written: dict[str, int] = {}

    from ledger_core.statements import statements_payload

    _write_json(out / "statements.json", statements_payload())
    manifest = json.loads(p.manifest.read_text(encoding="utf-8"))
    _write_json(out / "manifest.json", manifest)
    written["manifest.json"] = len(manifest["values"])

    # Every function's parquet results become JSON records for the pages.
    for folder in sorted(p.results.glob("f[0-9][0-9]")):
        for parquet in sorted(folder.glob("*.parquet")):
            frame = pl.read_parquet(parquet)
            target = out / folder.name / f"{parquet.stem}.json"
            _write_json(target, _records(frame))
            written[f"{folder.name}/{parquet.stem}.json"] = frame.height
        for extra in folder.glob("*.json"):
            if extra.name != "manifest.json":
                shutil.copy(extra, out / folder.name / extra.name)
                written[f"{folder.name}/{extra.name}"] = 1
    for name in ("bank_month", "bank_quarter", "bank_year", "bank_window"):
        frame = pl.read_parquet(p.results / "metrics" / f"{name}.parquet")
        _write_json(out / "metrics" / f"{name}.json", _records(frame))

    # The scorecard studio's inputs.
    studio = out / "studio"
    studio.mkdir(parents=True, exist_ok=True)
    folder = p.models_dir / "pd_scorecard"
    for name in ("scorecard_generated.json", "fine_bins_generated.json", "scorecard_uci.json"):
        if (folder / name).exists():
            shutil.copy(folder / name, studio / name)
    reasons = (p.rules / "reason_codes.yaml").read_text(encoding="utf-8")
    import yaml

    _write_json(studio / "reason_codes.json", yaml.safe_load(reasons))
    registry = json.loads((p.models_dir / "registry.json").read_text())
    _write_json(out / "models" / "registry.json", registry)

    # Documents rendered to HTML fragments: validation reports and the board pack.
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    for report in sorted((p.report / "validation").glob("*.md")):
        target = out / "reports" / f"{report.stem}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(md.render(report.read_text(encoding="utf-8")), encoding="utf-8")
        written[f"reports/{report.stem}.html"] = 1
    for doc, name in ((p.report / "board-pack.md", "board-pack"), (p.docs / "definitions.md", "definitions")):
        if doc.exists():
            (out / "reports" / f"{name}.html").write_text(
                md.render(doc.read_text(encoding="utf-8")), encoding="utf-8"
            )

    # Arrow IPC streams for ad hoc SQL in the browser. DuckDB-WASM inserts Arrow natively,
    # where reading parquet would make the browser fetch an extension from DuckDB's servers.
    explore = out / "explore"
    explore.mkdir(parents=True, exist_ok=True)
    schema = []
    for name, query in EXPLORE_QUERIES.items():
        table = con.execute(query).fetch_arrow_table()
        fields = [
            pa.field(f.name, pa.float64() if pa.types.is_decimal(f.type) else f.type) for f in table.schema
        ]
        table = table.cast(pa.schema(fields))
        with (
            pa.OSFile(str(explore / f"{name}.arrow"), "wb") as sink,
            pa.ipc.new_stream(sink, table.schema) as writer,
        ):
            writer.write_table(table)
        schema.append(
            {
                "table": name,
                "rows": table.num_rows,
                "columns": [{"name": f.name, "type": str(f.type)} for f in fields],
            }
        )
        written[f"explore/{name}.arrow"] = table.num_rows
    _write_json(explore / "schema.json", schema)
    return written


def main(p: Paths) -> dict[str, int]:
    from ledger_functions.warehouse import connect

    return export(p, connect(p))
