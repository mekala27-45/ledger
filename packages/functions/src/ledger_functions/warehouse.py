"""Build the dbt warehouse and open read only connections to it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
from ledger_core.paths import Paths


class WarehouseError(RuntimeError):
    pass


def dbt_env(p: Paths, *, staged: Path | None = None, database: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["LEDGER_STAGED"] = str((staged or p.staged).resolve())
    env["LEDGER_WAREHOUSE"] = str((database or p.warehouse_db).resolve())
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    return env


def build(
    p: Paths,
    *,
    staged: Path | None = None,
    database: Path | None = None,
    exclude: list[str] | None = None,
    command: str = "build",
    fresh: bool = True,
) -> None:
    """Run ``dbt build`` (models and every test) against staged parquet."""
    db = database or p.warehouse_db
    if fresh:
        for suffix in ("", ".wal"):
            Path(str(db) + suffix).unlink(missing_ok=True)
    dbt = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")
    args = [dbt, command, "--profiles-dir", ".", "--target", "dev", "--quiet"]
    if exclude:
        args += ["--exclude", *exclude]
    run = subprocess.run(
        args,
        cwd=p.warehouse_dir,
        env=dbt_env(p, staged=staged, database=database),
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        raise WarehouseError(f"dbt {command} failed:\n{run.stdout[-4000:]}\n{run.stderr[-2000:]}")


def connect(p: Paths, database: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = database or p.warehouse_db
    if not path.exists():
        raise WarehouseError(f"no warehouse at {path}; run `make warehouse`")
    return duckdb.connect(str(path), read_only=True)
