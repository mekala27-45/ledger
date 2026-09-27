"""The ledger reconciliation's three tests, plus the break locator's own properties."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ledger_functions.f11_controls.reconcile import Break, ReconciliationError, locate, reconcile

pytestmark = pytest.mark.warehouse


def _con(root: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(root / "warehouse.duckdb"), read_only=True)


def test_clean_ledger_reconciles_to_the_cent(clean_warehouse: Path) -> None:
    result = reconcile(_con(clean_warehouse))
    assert result.breaks == []
    assert result.unsourced_postings == 0
    assert result.clean
    assert result.accounts == 22 and result.months == 36


def test_injected_break_is_caught_and_located(broken_warehouse: Path) -> None:
    truth = pl.read_parquet(broken_warehouse / "data" / "raw" / "truth" / "truth_ledger_break.parquet").row(
        0, named=True
    )
    result = reconcile(_con(broken_warehouse))
    assert len(result.breaks) == 1, result.breaks
    (found,) = result.breaks
    assert found.kind == "reported_vs_postings"
    assert found.gl_account == truth["gl_account"]
    assert found.month == truth["month"]
    # Reported balances are debit positive, so an overstated deposit liability is a negative difference.
    assert abs(found.amount) == Decimal(str(truth["amount"]))
    assert result.unsourced_postings == 0


def test_an_empty_ledger_is_refused() -> None:
    con = duckdb.connect()
    con.execute("create schema staging")
    con.execute("create table staging.stg_gl_postings (posting_id bigint, amount decimal(18, 2))")
    con.execute(
        "create table staging.stg_gl_reported_balances (gl_account varchar, reported_balance decimal(18, 2))"
    )
    with pytest.raises(ReconciliationError, match="empty ledger"):
        reconcile(con)


def test_locator_reports_one_break_carried_forward() -> None:
    diffs = pl.DataFrame(
        {
            "gl_account": ["2010"] * 5,
            "month": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
            "difference": [
                Decimal("0"),
                Decimal("0"),
                Decimal("-4217.36"),
                Decimal("-4217.36"),
                Decimal("-4217.36"),
            ],
        }
    )
    assert locate(diffs, "k") == [Break("2010", "2026-03", Decimal("-4217.36"), 3, "k")]


@settings(max_examples=60, deadline=None)
@given(
    amounts=st.lists(st.integers(min_value=-(10**9), max_value=10**9), min_size=1, max_size=40),
    shock_at=st.integers(min_value=0, max_value=39),
    shock=st.integers(min_value=1, max_value=10**7),
)
def test_running_balance_equals_the_sum_of_postings_and_one_shock_is_one_break(
    amounts: list[int], shock_at: int, shock: int
) -> None:
    months = [f"2024-{i:03d}" for i in range(len(amounts))]
    postings = [Decimal(a) / 100 for a in amounts]
    running, total = [], Decimal("0")
    for p in postings:
        total += p
        running.append(total)
    assert running[-1] == sum(postings)
    at = min(shock_at, len(amounts) - 1)
    reported = [r + (Decimal(shock) / 100 if i >= at else 0) for i, r in enumerate(running)]
    diffs = pl.DataFrame(
        {
            "gl_account": ["x"] * len(months),
            "month": months,
            "difference": [a - b for a, b in zip(reported, running, strict=True)],
        }
    )
    found = locate(diffs, "k")
    assert found == [Break("x", months[at], Decimal(shock) / 100, len(months) - at, "k")]
