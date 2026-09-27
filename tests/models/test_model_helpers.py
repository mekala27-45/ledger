"""Helpers the BAF, attrition and cure trainers share with nothing else."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from ledger_models import train_baf as baf
from ledger_models import train_cure as cure


def _applications(n: int = 400, seed: int = 5) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    data: dict[str, object] = {c: rng.normal(size=n) for c in baf.NUMERIC}
    for c in baf.MISSING_AS_NEGATIVE:
        values = np.abs(rng.normal(size=n))
        values[rng.random(n) < 0.2] = -1.0
        data[c] = values
    for c in baf.CATEGORICAL:
        data[c] = rng.choice(["AA", "AB", "AC"], size=n).tolist()
    data["customer_age"] = rng.choice([20, 30, 40, 50, 60], size=n)
    data["fraud_bool"] = (rng.random(n) < 0.1).astype(int)
    data["month"] = rng.integers(0, 8, size=n)
    return pl.DataFrame(data)


def test_the_logistic_design_flags_every_missing_marker() -> None:
    frame = _applications()
    levels = {c: sorted(frame[c].unique().to_list()) for c in baf.CATEGORICAL}
    x = baf.logistic_design(frame, levels)
    width = len(baf.NUMERIC) + len(baf.MISSING_AS_NEGATIVE) + sum(len(v) - 1 for v in levels.values())
    assert x.shape == (frame.height, width)
    assert (x >= -10).all()
    # Where a marker said missing, the value column is zero and the flag column is one.
    first = baf.NUMERIC.index(baf.MISSING_AS_NEGATIVE[0])
    offset = sum(1 for c in baf.NUMERIC[:first] if c in baf.MISSING_AS_NEGATIVE)
    flag_col, value_col = first + offset, first + offset + 1
    missing = frame[baf.MISSING_AS_NEGATIVE[0]].to_numpy() < 0
    assert (x[missing, flag_col] == 1).all() and (x[missing, value_col] == 0).all()


def test_age_groups_split_where_the_suite_splits() -> None:
    frame = _applications()
    older = baf.older(frame)
    assert (older == (frame["customer_age"].to_numpy() >= baf.OLDER)).all()
    bands = set(baf.age_band(frame).tolist())
    assert bands <= {"under 30", "30 to 39", "40 to 49", "50 to 59", "60 and over"}


def test_the_single_feature_screen_finds_a_leaked_column() -> None:
    frame = _applications()
    train, test = frame.head(250), frame.tail(150)
    honest, _ = baf.univariate_screen(train, test)
    leaked = test.with_columns(income=pl.col("fraud_bool").cast(pl.Float64))
    worst, name = baf.univariate_screen(train, leaked)
    assert worst == pytest.approx(1.0) and name == "income"
    assert honest < 0.8


def test_the_suite_splits_by_month() -> None:
    train, val, test = baf.split(_applications())
    assert train["month"].max() <= baf.TRAIN_MONTHS[1]
    assert set(val["month"].unique().to_list()) <= {baf.VALIDATION_MONTH}
    assert test["month"].min() >= baf.TEST_MONTHS[0]


def test_cure_outcomes_are_known_before_its_test_months() -> None:
    assert cure.outcomes_known_before(cure.VALIDATION[1], cure.TEST[0])
    assert not cure.outcomes_known_before("2025-11", "2025-12")
    frame = pl.DataFrame({"month": ["2025-05", "2025-07", "2026-01"], "cured": [1, None, 0]})
    assert cure.part(frame, cure.TRAIN)["month"].to_list() == ["2025-05"]
