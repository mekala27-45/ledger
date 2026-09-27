"""The metric layer: every executive figure and ratio defined once, computed at four grains.

Measures come from one monthly mart. A flow is summed over a period, a balance is
the period's last month end, and an average balance is the mean of the period's
month ends. A ratio is always its components aggregated to the grain first and
divided second; averaging monthly ratios is the mistake this layer exists to stop.
The reconciliation proves the grains agree before anything is published.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import polars as pl
import yaml
from ledger_core.model import StrictModel

Grain = Literal["month", "quarter", "year", "window"]
GRAINS: tuple[Grain, ...] = ("month", "quarter", "year", "window")


class Measure(StrictModel):
    kind: Literal["flow", "balance", "average"]
    expr: str


class Metric(StrictModel):
    label: str
    definition: str
    numerator: str
    denominator: str | list[str]
    annualise: bool = False
    format: str


class MetricSpec(StrictModel):
    source: str
    grains: list[str]
    measures: dict[str, Measure]
    metrics: dict[str, Metric]


class MetricReconciliationError(AssertionError):
    pass


def load_spec(path: Path) -> MetricSpec:
    return MetricSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def monthly_frame(
    con: duckdb.DuckDBPyConnection, spec: MetricSpec, constants: dict[str, float]
) -> pl.DataFrame:
    """Evaluate every measure's expression per month, with config constants substituted."""
    selects = []
    for name, measure in spec.measures.items():
        expr = measure.expr.format(**constants)
        selects.append(f"({expr})::double as {name}")
    query = f"select month, month_index, quarter, year, {', '.join(selects)} from {spec.source} order by month_index"
    frame = con.execute(query).pl()
    if frame.height == 0:
        raise MetricReconciliationError(f"{spec.source} has no rows")
    return frame


def _period(grain: Grain) -> pl.Expr:
    if grain == "month":
        return pl.col("month")
    if grain == "quarter":
        return pl.col("quarter")
    if grain == "year":
        return pl.col("year").cast(pl.Utf8)
    return pl.lit("window")


def at_grain(monthly: pl.DataFrame, spec: MetricSpec, grain: Grain) -> pl.DataFrame:
    aggs: list[pl.Expr] = [
        pl.len().alias("months"),
        pl.col("month").min().alias("first_month"),
        pl.col("month").max().alias("last_month"),
    ]
    for name, measure in spec.measures.items():
        if measure.kind == "flow":
            aggs.append(pl.col(name).sum().alias(name))
        elif measure.kind == "balance":
            aggs.append(pl.col(name).sort_by("month_index").last().alias(name))
        else:
            aggs.append(pl.col(name).mean().alias(name))
    frame = (
        monthly.with_columns(period=_period(grain))
        .group_by("period", maintain_order=True)
        .agg(aggs)
        .sort("first_month")
    )
    for name, metric in spec.metrics.items():
        denominators = [metric.denominator] if isinstance(metric.denominator, str) else metric.denominator
        den = pl.sum_horizontal([pl.col(d) for d in denominators])
        num = pl.col(metric.numerator) * (12.0 / pl.col("months") if metric.annualise else 1.0)
        frame = frame.with_columns(pl.when(den != 0).then(num / den).otherwise(None).alias(name))
    return frame.with_columns(pl.lit(grain).alias("grain"))


@dataclass(frozen=True)
class Check:
    name: str
    grain: str
    worst: float
    passed: bool


def reconcile(monthly: pl.DataFrame, spec: MetricSpec, tolerance: float = 0.005) -> list[Check]:
    """Hold every grain to the monthly truth. Raises if any check fails."""
    frames = {g: at_grain(monthly, spec, g) for g in GRAINS}
    checks: list[Check] = []
    window = frames["window"].row(0, named=True)
    last = monthly.sort("month_index").row(-1, named=True)
    for name, measure in spec.measures.items():
        for grain in ("month", "quarter", "year"):
            frame = frames[grain]
            if measure.kind == "flow":
                worst = abs(float(frame[name].sum()) - float(window[name]))
            elif measure.kind == "balance":
                worst = abs(float(frame.sort("first_month")[name][-1]) - float(last[name]))
            else:
                weighted = float((frame[name] * frame["months"]).sum() / frame["months"].sum())
                worst = abs(weighted - float(window[name]))
            checks.append(Check(f"{measure.kind}:{name}", grain, worst, worst <= tolerance))
    for grain, frame in frames.items():
        identity = (
            (
                frame["net_interest_income"]
                + frame["noninterest_income"]
                - frame["noninterest_expense"]
                - frame["provision"]
                - frame["tax"]
                - frame["net_income"]
            )
            .abs()
            .max()
        )
        worst = float(identity) if identity is not None else 0.0
        checks.append(Check("identity:net_income", grain, worst, worst <= tolerance))
        for name, metric in spec.metrics.items():
            denominators = [metric.denominator] if isinstance(metric.denominator, str) else metric.denominator
            den = sum((frame[d] for d in denominators), start=pl.Series([0.0] * frame.height))
            factor = 12.0 / frame["months"] if metric.annualise else 1.0
            recomputed = frame[metric.numerator] * factor / den
            gap = (recomputed - frame[name]).abs().max()
            worst = float(gap) if gap is not None else 0.0
            checks.append(Check(f"ratio:{name}", grain, worst, worst <= 1e-12))
    failed = [c for c in checks if not c.passed]
    if failed:
        raise MetricReconciliationError(f"{len(failed)} metric checks failed: {failed[:5]}")
    return checks


def constants_from_config(risk_weights: dict[str, float]) -> dict[str, float]:
    return {f"risk_weight_{k}": v for k, v in risk_weights.items()}
