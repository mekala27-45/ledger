"""The twelve functions in the order a head of analytics walks them on a Monday."""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest
from ledger_core.paths import Paths

from ledger_functions.base import FunctionSpec, new_context
from ledger_functions.policy import policy_manifest
from ledger_functions.warehouse import connect

MODULES = (
    "ledger_functions.f01_executive",
    "ledger_functions.f02_lending",
    "ledger_functions.f03_fair_lending",
    "ledger_functions.f04_desk",
    "ledger_functions.f05_crime",
    "ledger_functions.f06_deposits",
    "ledger_functions.f07_complaints",
    "ledger_functions.f08_treasury",
    "ledger_functions.f09_collections",
    "ledger_functions.f10_model_risk",
    "ledger_functions.f11_controls",
    "ledger_functions.f12_boardpack",
)


def available() -> list[FunctionSpec]:
    """Every function module that exists in this checkout, in walk order."""
    specs: list[FunctionSpec] = []
    for name in MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name == name:
                continue
            raise
        spec = getattr(module, "SPEC", None)
        if isinstance(spec, FunctionSpec):
            specs.append(spec)
    return specs


def run_functions(p: Paths, cfg: LedgerConfig, only: list[str] | None = None) -> dict[str, float]:
    timings: dict[str, float] = {}
    con = connect(p)
    for spec in available():
        if only and spec.code not in only:
            continue
        started = time.time()
        ctx = new_context(p, cfg, con, spec.code)
        spec.run(ctx)
        ctx.out.mkdir(parents=True, exist_ok=True)
        ctx.manifest.save(ctx.out / "manifest.json")
        timings[spec.code] = round(time.time() - started, 1)
    return timings


def partial_manifests(p: Paths) -> list[Path]:
    """Function and model manifests, in a stable order."""
    found = sorted(p.results.glob("f[0-9][0-9]/manifest.json"))
    found += sorted(p.models_dir.glob("*/manifest.json"))
    return found


def merge_manifest(p: Paths, cfg: LedgerConfig) -> Manifest:
    merged = policy_manifest(cfg)
    for path in partial_manifests(p):
        merged.merge(Manifest.load(path))
    merged.save(p.manifest)
    return merged


def manifest_summary(m: Manifest) -> str:
    return json.dumps(m.counts())
