"""What every function module receives and what it must produce.

A function module answers one line of business or control function's question
the way the Day 7 module shape asks: question, method, chart with a written
callout, test, limitation. It reads the warehouse through a read only
connection, writes its tables to results/<code>/, and puts every number it
publishes into its own partial manifest, which ``ledger manifest`` merges.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import polars as pl
from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest
from ledger_core.paths import Paths


@dataclass
class Context:
    paths: Paths
    config: LedgerConfig
    con: duckdb.DuckDBPyConnection
    manifest: Manifest
    out: Path
    notes: list[str] = field(default_factory=list)

    def save(self, name: str, frame: pl.DataFrame) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / f"{name}.parquet"
        frame.write_parquet(path, compression="zstd", statistics=False)
        return path

    def sql(self, query: str, params: list[object] | None = None) -> pl.DataFrame:
        return self.con.execute(query, params or []).pl()


@dataclass(frozen=True)
class FunctionSpec:
    code: str
    slug: str
    title: str
    question: str
    run: Callable[[Context], None]


def new_context(p: Paths, cfg: LedgerConfig, con: duckdb.DuckDBPyConnection, code: str) -> Context:
    manifest = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
    return Context(paths=p, config=cfg, con=con, manifest=manifest, out=p.results / code)
