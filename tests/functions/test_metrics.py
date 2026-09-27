"""The metric layer reconciles across month, quarter, year and window, and catches an averaged ratio."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ledger_functions import metrics as ml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ml.load_spec(ROOT / "metrics" / "bank.yaml")
COLUMNS = [
    "cash",
    "securities",
    "loans_installment",
    "loans_card",
    "loans_mortgage",
    "total_loans",
    "allowance",
    "total_assets",
    "total_deposits",
    "total_equity",
    "earning_assets",
    "interest_income_loans",
    "interest_income_securities",
    "interest_expense_deposits",
    "interest_expense_borrowings",
    "noninterest_income",
    "provision",
    "noninterest_expense",
    "tax",
    "nonperforming_loans",
]
WEIGHTS = {"cash": 0.0, "securities": 0.2, "mortgage": 0.5, "installment": 1.0, "card": 1.0}


def _monthly(values: list[float]) -> pl.DataFrame:
    months = [f"{2024 + (i // 12)}-{i % 12 + 1:02d}" for i in range(len(values))]
    base = {c: [v * (k + 1) for v in values] for k, c in enumerate(COLUMNS)}
    frame = pl.DataFrame({"month": months, "month_index": list(range(len(values))), **base})
    frame = frame.with_columns(
        quarter=pl.col("month").str.slice(0, 4)
        + "Q"
        + ((pl.col("month").str.slice(5, 2).cast(pl.Int32) - 1) // 3 + 1).cast(pl.Utf8),
        year=pl.col("month").str.slice(0, 4).cast(pl.Int32),
        net_income=pl.col("interest_income_loans")
        + pl.col("interest_income_securities")
        - pl.col("interest_expense_deposits")
        - pl.col("interest_expense_borrowings")
        + pl.col("noninterest_income")
        - pl.col("provision")
        - pl.col("noninterest_expense")
        - pl.col("tax"),
    )
    constants = ml.constants_from_config(WEIGHTS)
    exprs = [
        pl.sql_expr(m.expr.format(**constants)).cast(pl.Float64).alias(n) for n, m in SPEC.measures.items()
    ]
    return frame.select("month", "month_index", "quarter", "year", *exprs)


def test_grains_reconcile_on_a_clean_history() -> None:
    checks = ml.reconcile(_monthly([1.0 + 0.1 * i for i in range(20)]), SPEC)
    assert checks and all(c.passed for c in checks)
    assert {c.grain for c in checks} == {"month", "quarter", "year", "window"}


def test_an_averaged_ratio_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    real = ml.at_grain

    def averaged(monthly: pl.DataFrame, spec: ml.MetricSpec, grain: ml.Grain) -> pl.DataFrame:
        frame = real(monthly, spec, grain)
        if grain == "month":
            return frame
        # The mistake: the mean of monthly ratios instead of the ratio of summed components.
        keys = monthly.select(pl.col("month").alias("period"), "quarter", "year")
        monthly_ratios = (
            real(monthly, spec, "month").join(keys, on="period").with_columns(period=ml._period(grain))
        )
        means = monthly_ratios.group_by("period").agg(pl.col("nim").mean().alias("nim_avg"))
        return frame.join(means, on="period").with_columns(nim=pl.col("nim_avg")).drop("nim_avg")

    monkeypatch.setattr(ml, "at_grain", averaged)
    with pytest.raises(ml.MetricReconciliationError):
        ml.reconcile(_monthly([1.0 + ((-1) ** i) * 0.5 for i in range(24)]), SPEC)


def test_an_empty_source_is_refused() -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("create schema marts")
    con.execute(
        "create table marts.mart_bank_month as select * from (select '2024-01' as month, 0 as month_index, "
        "'2024Q1' as quarter, 2024 as year, "
        + ", ".join(f"0.0 as {c}" for c in COLUMNS + ["net_income"])
        + ") where false"
    )
    with pytest.raises(ml.MetricReconciliationError, match="no rows"):
        ml.monthly_frame(con, SPEC, ml.constants_from_config(WEIGHTS))


@settings(max_examples=30, deadline=None)
@given(st.lists(st.floats(min_value=0.5, max_value=50.0), min_size=3, max_size=30))
def test_flows_sum_the_same_at_every_grain(values: list[float]) -> None:
    monthly = _monthly(values)
    totals = {g: ml.at_grain(monthly, SPEC, g)["net_income"].sum() for g in ml.GRAINS}
    assert max(totals.values()) - min(totals.values()) < 1e-6 * max(1.0, abs(totals["window"]))
