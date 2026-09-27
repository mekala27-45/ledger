"""Promotion gates. A model is promoted to its role only if every gate passes.

Each gate states its threshold before the model is evaluated, compares one
measured value, and records the result. The gates are the same shape for every
model; the thresholds are the model's own, set in its training module and quoted
in its validation report.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Comparison = Literal["at_least", "at_most", "between"]


@dataclass(frozen=True)
class Gate:
    name: str
    statement: str
    comparison: Comparison
    threshold: float
    upper: float | None = None
    critical: bool = True

    def check(self, value: float | None) -> GateResult:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return GateResult(self, value, False, "not measured")
        if self.comparison == "at_least":
            ok = value >= self.threshold
        elif self.comparison == "at_most":
            ok = value <= self.threshold
        else:
            assert self.upper is not None
            ok = self.threshold <= value <= self.upper
        return GateResult(self, value, ok, "pass" if ok else "fail")


@dataclass(frozen=True)
class GateResult:
    gate: Gate
    value: float | None
    passed: bool
    note: str


class GateError(RuntimeError):
    pass


def run_gates(gates: list[Gate], measured: Mapping[str, float | None]) -> list[GateResult]:
    if not gates:
        raise GateError("refusing to promote with no gates")
    unknown = [g.name for g in gates if g.name not in measured]
    if unknown:
        raise GateError(f"gates with no measurement supplied: {unknown}")
    return [g.check(measured[g.name]) for g in gates]


def conclusion(results: list[GateResult]) -> tuple[str, list[str]]:
    """Approved, approved with conditions (a non critical gate failed), or not approved."""
    failed_critical = [r for r in results if not r.passed and r.gate.critical]
    failed_other = [r for r in results if not r.passed and not r.gate.critical]
    if failed_critical:
        return "not approved", [f"{r.gate.statement} (measured {_fmt(r.value)})" for r in failed_critical]
    if failed_other:
        return "approved with conditions", [
            f"Remediate before the next validation: {r.gate.statement} (measured {_fmt(r.value)})"
            for r in failed_other
        ]
    return "approved", []


def _fmt(value: float | None) -> str:
    return "nothing" if value is None else f"{value:.4g}"
