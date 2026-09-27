"""The ``ledger`` command: one subcommand per pipeline stage, in the Makefile's order."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from ledger_core.paths import Paths, paths

Command = Callable[[Paths, argparse.Namespace], int]
COMMANDS: dict[str, tuple[str, Command]] = {}


def command(name: str, help_text: str) -> Callable[[Command], Command]:
    def register(fn: Command) -> Command:
        COMMANDS[name] = (help_text, fn)
        return fn

    return register


@command("generate", "run the seeded core banking generator into data/raw")
def _generate(p: Paths, args: argparse.Namespace) -> int:
    from ledger_bankgen.generate import generate
    from ledger_bankgen.params import GeneratorParams

    params = GeneratorParams()
    if args.customers:
        params = params.scaled(args.customers)
    summary = generate(params, p.generated, p.raw / "truth")
    print(json.dumps(summary.tables))
    return 0


@command("ingest", "normalise the real public datasets into data/staged/real")
def _ingest(p: Paths, args: argparse.Namespace) -> int:
    from ledger_contracts.ingest import stage_all

    for staged in stage_all(p):
        print(f"{staged.name:32s} {staged.rows:>10,d}")
    return 0


@command("contracts", "validate every raw table, quarantine by rule, scan for identifiers, stage")
def _contracts(p: Paths, args: argparse.Namespace) -> int:
    from ledger_contracts.run import run_contracts

    summary = run_contracts(p, include_real=not args.generated_only)
    print(json.dumps({"tables": len(summary["tables"]), "identifiers": summary["identifiers"]}))  # type: ignore[arg-type]
    return 0


@command("warehouse", "build the dbt warehouse over the staged tables and run every dbt test")
def _warehouse(p: Paths, args: argparse.Namespace) -> int:
    from ledger_functions.warehouse import build

    build(p)
    return 0


@command("reconcile", "reconcile the general ledger to its postings and sub ledgers, to the cent")
def _reconcile(p: Paths, args: argparse.Namespace) -> int:
    from ledger_functions.f11_controls.reconcile import reconcile
    from ledger_functions.warehouse import connect

    result = reconcile(connect(p))
    out = p.results / "f11"
    out.mkdir(parents=True, exist_ok=True)
    result.table.write_parquet(out / "reconciliation.parquet")
    result.subledger.write_parquet(out / "subledger_tie.parquet")
    breaks = [
        {
            "gl_account": b.gl_account,
            "month": b.month,
            "amount": str(b.amount),
            "months_carried": b.months_carried,
            "kind": b.kind,
        }
        for b in result.breaks
    ]
    (out / "breaks.json").write_text(json.dumps(breaks, indent=1) + "\n")
    print(json.dumps({"breaks": breaks, "unsourced_postings": result.unsourced_postings}))
    return 0


@command("metrics", "compute the metric layer at four grains and reconcile the grains")
def _metrics(p: Paths, args: argparse.Namespace) -> int:
    from ledger_core.config import load_config

    from ledger_functions import metrics as ml
    from ledger_functions.warehouse import connect

    cfg = load_config(p.config)
    spec = ml.load_spec(p.metrics / "bank.yaml")
    monthly = ml.monthly_frame(connect(p), spec, ml.constants_from_config(cfg.capital.risk_weights))
    checks = ml.reconcile(monthly, spec)
    out = p.results / "metrics"
    out.mkdir(parents=True, exist_ok=True)
    for grain in ml.GRAINS:
        ml.at_grain(monthly, spec, grain).write_parquet(out / f"bank_{grain}.parquet")
    import polars as pl

    pl.DataFrame([c.__dict__ for c in checks]).write_parquet(out / "reconciliation.parquet")
    print(json.dumps({"checks": len(checks), "failed": sum(not c.passed for c in checks)}))
    return 0


@command("models", "train, evaluate, gate and document the models under the contract")
def _models(p: Paths, args: argparse.Namespace) -> int:
    from ledger_core.config import load_config
    from ledger_models import runner

    from ledger_functions.warehouse import connect

    timings = runner.run_models(
        connect(p), load_config(p.config), p.root, p.models_dir, only=args.only or None
    )
    print(json.dumps(timings))
    return 0


@command("functions", "run the function modules f01 to f12 over the warehouse and the model results")
def _functions(p: Paths, args: argparse.Namespace) -> int:
    from ledger_core.config import load_config

    from ledger_functions.registry import run_functions

    timings = run_functions(p, load_config(p.config), only=args.only or None)
    print(json.dumps(timings))
    return 0


@command("manifest", "merge policy, function and model results into results/manifest.json")
def _manifest(p: Paths, args: argparse.Namespace) -> int:
    from ledger_core.config import load_config

    from ledger_functions.registry import manifest_summary, merge_manifest

    print(manifest_summary(merge_manifest(p, load_config(p.config))))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger", description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: discovered)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, _) in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text)
        if name == "generate":
            cmd.add_argument("--customers", type=int, default=0, help="scale the bank to this many customers")
        if name == "contracts":
            cmd.add_argument("--generated-only", action="store_true", help="skip the real datasets")
        if name in {"functions", "models"}:
            cmd.add_argument("--only", nargs="*", default=[], help="run only these codes")
        if name in EXTRA_ARGS:
            EXTRA_ARGS[name](cmd)
    return parser


EXTRA_ARGS: dict[str, Callable[[argparse.ArgumentParser], None]] = {}


def app(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    p = Paths(args.root.resolve()) if args.root else paths()
    started = time.time()
    _, fn = COMMANDS[args.command]
    code = fn(p, args)
    print(f"ledger {args.command}: {time.time() - started:.1f}s", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(app())
