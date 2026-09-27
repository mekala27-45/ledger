"""Build the dbt warehouse and open read only connections to it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
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


def build_args(
    p: Paths,
    *,
    database: Path | None = None,
    exclude: list[str] | None = None,
    command: str = "build",
) -> list[str]:
    """The dbt command line for a build into ``database``.

    A build into any database other than the warehouse's own keeps dbt's artifacts beside
    that database. dbt writes them under the project folder by default, and the controls
    function publishes its model and test counts from ``warehouse/target``, so a small test
    build must never overwrite the last full build's record there.
    """
    dbt = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")
    args = [dbt, command, "--profiles-dir", ".", "--target", "dev", "--quiet"]
    if database is not None and database.resolve() != p.warehouse_db.resolve():
        artifacts = database.resolve().parent / "dbt"
        args += ["--target-path", str(artifacts / "target"), "--log-path", str(artifacts / "logs")]
    if exclude:
        args += ["--exclude", *exclude]
    return args


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
    run = subprocess.run(
        build_args(p, database=database, exclude=exclude, command=command),
        cwd=p.warehouse_dir,
        env=dbt_env(p, staged=staged, database=database),
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        raise WarehouseError(f"dbt {command} failed:\n{run.stdout[-4000:]}\n{run.stderr[-2000:]}")


@dataclass(frozen=True)
class BuildRecord:
    models: int
    tests: int
    tests_passed: int


def last_full_build(run_results: Path) -> BuildRecord:
    """Model and test counts from dbt's record of the warehouse's last build.

    Refuses a record that is missing or that came from a partial build (a selection, an
    exclusion or a single command other than ``build``), because a count published from it
    would describe some other warehouse than the one the functions read.
    """
    if not run_results.exists():
        raise WarehouseError(f"no dbt run record at {run_results}; run `make warehouse`")
    record = json.loads(run_results.read_text(encoding="utf-8"))
    args = record.get("args", {})
    if args.get("which") != "build" or args.get("select") or args.get("exclude"):
        raise WarehouseError(
            f"{run_results} records a partial dbt run (command {args.get('which')!r}, "
            f"select {args.get('select')!r}, exclude {args.get('exclude')!r}); run `make warehouse`"
        )
    results = record.get("results", [])
    tests = [r for r in results if r["unique_id"].startswith("test.")]
    models = [r for r in results if r["unique_id"].startswith("model.")]
    if not models:
        raise WarehouseError(f"{run_results} records no models")
    return BuildRecord(
        models=len(models),
        tests=len(tests),
        tests_passed=sum(r["status"] == "pass" for r in tests),
    )


def connect(p: Paths, database: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = database or p.warehouse_db
    if not path.exists():
        raise WarehouseError(f"no warehouse at {path}; run `make warehouse`")
    return duckdb.connect(str(path), read_only=True)
