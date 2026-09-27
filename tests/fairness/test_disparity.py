"""Disparity measures: known answers, deliberate violations, and refusals."""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest
from ledger_fairness.disparity import (
    adjusted_odds_ratios,
    benjamini_hochberg,
    design_matrix,
    rate_ratio,
    unadjusted_table,
)

PROTECTED = {"derived_race", "derived_sex", "county_fips", "applicant_age"}


def test_rate_ratio_known_answer() -> None:
    r = rate_ratio(200, 1000, 100, 1000)
    assert r.ratio == pytest.approx(2.0)
    se = math.sqrt(1 / 200 - 1 / 1000 + 1 / 100 - 1 / 1000)
    assert r.low == pytest.approx(2.0 * math.exp(-1.959963984540054 * se))
    assert r.low < 2.0 < r.high
    assert r.p_value < 0.001
    # The same rates on a tenth of the applications cannot tell the groups apart.
    small = rate_ratio(20, 100, 10, 100)
    assert small.ratio == pytest.approx(2.0)
    assert small.low < 1.0 < small.high


def test_rate_ratio_refuses_empty_groups() -> None:
    with pytest.raises(ValueError):
        rate_ratio(0, 100, 10, 100)
    with pytest.raises(ValueError):
        rate_ratio(5, 0, 10, 100)
    with pytest.raises(ValueError):
        rate_ratio(120, 100, 10, 100)


def test_benjamini_hochberg_matches_the_procedure_by_hand() -> None:
    p = [0.01, 0.04, 0.03, 0.005]
    # Ranked 0.005, 0.01, 0.03, 0.04 -> scaled 0.02, 0.02, 0.04, 0.04, already monotone.
    assert benjamini_hochberg(p).tolist() == pytest.approx([0.02, 0.04, 0.04, 0.02])
    from statsmodels.stats.multitest import multipletests

    rng = np.random.default_rng(1)
    q = rng.random(40) ** 3
    assert benjamini_hochberg(q) == pytest.approx(multipletests(q, method="fdr_bh")[1])


def test_benjamini_hochberg_refuses_nothing_and_nonsense() -> None:
    with pytest.raises(ValueError):
        benjamini_hochberg([])
    with pytest.raises(ValueError):
        benjamini_hochberg([0.2, 1.4])


def _simulated(n: int = 40_000, group_effect: float = 0.7, seed: int = 5) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    group = rng.choice(["A", "B"], size=n, p=[0.7, 0.3])
    # Group B also carries more debt, so part of its raw gap is explained by the control.
    debt = rng.normal(0, 1, n) + np.where(group == "B", 0.8, 0.0)
    logit = -2.0 + 0.9 * debt + np.where(group == "B", group_effect, 0.0)
    denied = rng.random(n) < 1 / (1 + np.exp(-logit))
    lender = rng.choice(["L1", "L2", "L3"], size=n)
    return pl.DataFrame({"derived_race": group, "debt": debt, "lender": lender, "denied": denied})


def test_adjustment_recovers_a_planted_group_effect() -> None:
    frame = _simulated(group_effect=0.7)
    table, r2 = adjusted_odds_ratios(frame, "denied", {"derived_race": "A"}, ["debt"], ["lender"], PROTECTED)
    row = table.row(0, named=True)
    assert row["group"] == "B"
    assert row["low"] < math.exp(0.7) < row["high"]
    assert 0 < r2 < 1


def test_adjustment_removes_a_gap_the_controls_explain() -> None:
    frame = _simulated(group_effect=0.0)
    raw = unadjusted_table(frame, "denied", "derived_race", "A")
    assert raw.filter(pl.col("group") == "B")["ratio"][0] > 1.3
    table, _ = adjusted_odds_ratios(frame, "denied", {"derived_race": "A"}, ["debt"], ["lender"], PROTECTED)
    row = table.row(0, named=True)
    assert row["low"] < 1.0 < row["high"]


def test_a_protected_attribute_or_proxy_is_refused_as_a_control() -> None:
    frame = _simulated().with_columns(county_fips=pl.lit("34013"), applicant_age=pl.lit(40.0))
    with pytest.raises(ValueError, match="protected attributes or proxies"):
        design_matrix(frame, {"derived_race": "A"}, ["applicant_age"], [], PROTECTED)
    with pytest.raises(ValueError, match="protected attributes or proxies"):
        design_matrix(frame, {"derived_race": "A"}, ["debt"], ["county_fips"], PROTECTED)


def test_unadjusted_table_refuses_a_missing_reference() -> None:
    frame = _simulated()
    with pytest.raises(ValueError, match="reference group"):
        unadjusted_table(frame, "denied", "derived_race", "Z")
