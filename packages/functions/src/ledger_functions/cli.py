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
