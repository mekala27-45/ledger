"""Run the model trainers in dependency order."""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from pathlib import Path

import duckdb
from ledger_core.config import LedgerConfig

Trainer = Callable[[duckdb.DuckDBPyConnection, LedgerConfig, Path, Path], object]

# model ids trained by each module; a module may train more than one model.
TRAINERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ledger_models.train_pd", ("pd_scorecard", "pd_challenger")),
    ("ledger_desk.train", ("fraud_card",)),
    ("ledger_models.train_baf", ("fraud_account",)),
    ("ledger_crime.train", ("aml_triage",)),
    ("ledger_models.train_attrition", ("attrition",)),
    ("ledger_nlp.train", ("relief",)),
    ("ledger_models.train_cure", ("cure",)),
)


def run_models(
    con: duckdb.DuckDBPyConnection,
    cfg: LedgerConfig,
    root: Path,
    models_dir: Path,
    only: list[str] | None = None,
) -> dict[str, float]:
    timings: dict[str, float] = {}
    for module_name, ids in TRAINERS:
        if only and not set(ids) & set(only):
            continue
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        started = time.time()
        module.run(con, cfg, root, models_dir)
        timings["+".join(ids)] = round(time.time() - started, 1)
    return timings
