from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import polars as pl
import pytest
from ledger_core.pit import LeakageError, PointInTimeFrame, recompute_check


def _history() -> PointInTimeFrame:
    base = datetime(2026, 1, 1)
    rows = [
        {"entity": e, "t": base + timedelta(hours=h), "amount": float(h)}
        for e in ("a", "b")
        for h in range(0, 48, 3)
    ]
    return PointInTimeFrame.build(pl.DataFrame(rows), "entity", "t")


def _count_before(past: pl.DataFrame, row: dict[str, Any]) -> dict[str, float]:
    return {"n_prior": float(past.height), "sum_prior": float(past["amount"].sum()) if past.height else 0.0}


def _features(history: PointInTimeFrame, *, leak: bool) -> pl.DataFrame:
    frame = history.frame.with_columns(
        n_prior=pl.int_range(pl.len()).over("entity").cast(pl.Float64) + (1.0 if leak else 0.0),
        sum_prior=(pl.col("amount").cum_sum().over("entity") - pl.col("amount")),
    )
    return frame.rename({"t": "prediction_time"})


def test_correct_features_pass_the_recompute_check() -> None:
    h = _history()
    assert (
        recompute_check(
            _features(h, leak=False), h, "prediction_time", _count_before, ["n_prior", "sum_prior"]
        )
        == 32
    )


def test_a_feature_that_counts_the_current_event_is_caught() -> None:
    h = _history()
    with pytest.raises(LeakageError):
        recompute_check(_features(h, leak=True), h, "prediction_time", _count_before, ["n_prior"])


def test_refuses_an_empty_feature_table() -> None:
    h = _history()
    with pytest.raises(ValueError, match="empty"):
        recompute_check(
            pl.DataFrame({"entity": [], "prediction_time": []}), h, "prediction_time", _count_before, []
        )
