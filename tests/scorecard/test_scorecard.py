"""Scorecard identities: binning, WoE, IV, points, probabilities and reason codes."""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ledger_scorecard.binning import coarse_classing, fine_classing, woe_of
from ledger_scorecard.scorecard import (
    ProxyError,
    Scaling,
    Scorecard,
    adverse_action_reasons,
    check_proxies,
    fit_scorecard,
    psi,
)

SCALING = Scaling(base_score=600, base_odds=30, pdo=20)
PROXIES = {"applicant_age", "zip5", "race", "sex"}
REASONS = {
    "utilization": "Proportion of revolving balances to credit limits is too high",
    "score": "Credit bureau score is too low",
    "housing": "Housing status",
    "noise": "Other",
}


def _data(n: int = 6000, seed: int = 7) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    score = rng.normal(680, 60, n)
    utilization = np.clip(rng.beta(2, 3, n), 0, 1)
    housing = rng.choice(["own", "rent", "mortgage"], n, p=[0.3, 0.4, 0.3])
    noise = rng.normal(0, 1, n)
    z = -2.2 - 0.02 * (score - 680) + 2.0 * (utilization - 0.4) + np.where(housing == "rent", 0.4, 0.0)
    bad = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    score[rng.random(n) < 0.03] = np.nan
    return pl.DataFrame(
        {"score": score, "utilization": utilization, "housing": housing, "noise": noise, "bad": bad}
    )


def _card() -> tuple[Scorecard, pl.DataFrame]:
    frame = _data()
    card = fit_scorecard(
        frame,
        "bad",
        ["score", "utilization", "housing", "noise"],
        categorical={"housing"},
        scaling=SCALING,
        cutoff=560,
        proxies=PROXIES,
    )
    return card, frame


def test_scaling_matches_the_stated_convention() -> None:
    assert SCALING.factor == pytest.approx(20 / math.log(2))
    assert SCALING.probability_of_bad(600) == pytest.approx(1 / 31)
    assert SCALING.probability_of_bad(620) == pytest.approx(1 / 61)


def test_points_convert_back_to_the_logistic_probability() -> None:
    card, frame = _card()
    assert np.allclose(card.probability(frame), card.logistic_probability(frame), atol=1e-10)


def test_coarse_bins_are_monotone_and_hold_their_share() -> None:
    frame = _data()
    fine = fine_classing(frame["utilization"].to_numpy(), frame["bad"].to_numpy(), "utilization", max_bins=20)
    coarse = coarse_classing(fine, min_bin_share=0.05)
    assert coarse.is_monotone()
    assert min(coarse.shares()) >= 0.05 - 1e-12
    assert coarse.direction == -1  # more utilization, fewer goods per bad


def test_missing_values_keep_their_own_bin() -> None:
    frame = _data()
    fine = fine_classing(frame["score"].to_numpy(), frame["bad"].to_numpy(), "score")
    coarse = coarse_classing(fine)
    assert sum(b.is_missing for b in coarse.bins) == 1
    assert coarse.is_monotone()


def test_information_value_is_non_negative_and_the_sum_over_bins() -> None:
    card, _ = _card()
    for c in card.characteristics:
        contributions = c.table.iv_contributions()
        assert all(x >= 0 for x in contributions)
        assert c.table.iv() == pytest.approx(sum(contributions))
        assert card.iv[c.name] == pytest.approx(c.table.iv())


def test_noise_is_dropped_below_the_information_value_floor() -> None:
    card, _ = _card()
    assert "noise" in card.dropped
    assert {c.name for c in card.characteristics} == {"score", "utilization", "housing"}


def test_points_rise_with_weight_of_evidence_within_every_characteristic() -> None:
    card, _ = _card()
    for c in card.characteristics:
        order = np.argsort(c.table.woe())
        assert all(np.diff(np.asarray(c.points)[order]) >= -1e-9)


def test_reasons_are_the_largest_shortfalls_and_empty_for_approvals() -> None:
    card, frame = _card()
    scores = card.score(frame)
    declined = frame.filter(pl.Series(scores < card.cutoff)).head(25)
    approved = frame.filter(pl.Series(scores >= card.cutoff)).head(25)
    assert declined.height and approved.height
    for i in range(declined.height):
        row = declined.slice(i, 1)
        reasons = adverse_action_reasons(card, row, REASONS, PROXIES, top=4)
        assert 1 <= len(reasons) <= 4
        gaps = [r.shortfall for r in reasons]
        assert gaps == sorted(gaps, reverse=True)
        points = card.assign(row)[0]
        all_gaps = sorted(
            (c.max_points - p for c, p in zip(card.characteristics, points, strict=True)), reverse=True
        )
        assert gaps == pytest.approx([g for g in all_gaps if g > 1e-9][: len(gaps)])
    for i in range(approved.height):
        assert adverse_action_reasons(card, approved.slice(i, 1), REASONS, PROXIES) == []


def test_a_proxy_can_never_be_a_feature_or_a_reason() -> None:
    with pytest.raises(ProxyError):
        check_proxies(["score", "applicant_age"], PROXIES)
    frame = _data().with_columns(zip5=pl.lit("07030"))
    with pytest.raises(ProxyError):
        fit_scorecard(
            frame,
            "bad",
            ["score", "zip5"],
            categorical={"zip5"},
            scaling=SCALING,
            cutoff=560,
            proxies=PROXIES,
        )


def test_the_scorecard_survives_a_round_trip() -> None:
    card, frame = _card()
    again = Scorecard.from_dict(card.to_dict())
    assert np.allclose(again.score(frame), card.score(frame))


def test_refusals() -> None:
    with pytest.raises(ValueError, match="no observations"):
        fine_classing(np.array([]), np.array([]), "x")
    frame = _data().with_columns(bad=pl.lit(0))
    with pytest.raises(ValueError, match="single outcome"):
        fit_scorecard(
            frame, "bad", ["score"], categorical=set(), scaling=SCALING, cutoff=560, proxies=PROXIES
        )
    with pytest.raises(ValueError, match="empty"):
        psi(np.array([]), np.array([1.0]))


def test_population_stability() -> None:
    rng = np.random.default_rng(1)
    base = rng.normal(600, 50, 5000)
    assert psi(base, base) == pytest.approx(0.0, abs=1e-9)
    assert psi(base, base + 40) > 0.25


@settings(max_examples=40, deadline=None)
@given(
    goods=st.lists(st.integers(min_value=0, max_value=500), min_size=2, max_size=12),
    bads=st.lists(st.integers(min_value=0, max_value=500), min_size=2, max_size=12),
)
def test_iv_contributions_are_never_negative(goods: list[int], bads: list[int]) -> None:
    n = min(len(goods), len(bads))
    g, b = goods[:n], bads[:n]
    total_g, total_b = sum(g) or 1, sum(b) or 1
    for gi, bi in zip(g, b, strict=True):
        w = woe_of(gi, bi, total_g, total_b)
        gs, bs = (gi + 0.5, bi + 0.5) if gi == 0 or bi == 0 else (gi, bi)
        assert (gs / total_g - bs / total_b) * w >= -1e-12


def test_committed_reason_table_and_proxy_list_are_disjoint() -> None:
    from pathlib import Path

    from ledger_scorecard.policy_files import load_proxies, load_reason_codes

    rules = Path(__file__).resolve().parents[2] / "rules"
    proxies = load_proxies(rules)
    assert {"applicant_age", "applicant_zip5", "county_fips", "education", "marriage"} <= proxies
    for population in ("generated", "uci"):
        reasons = load_reason_codes(rules, population)
        assert not set(reasons) & proxies
        assert all(len(text) > 10 for text in reasons.values())
