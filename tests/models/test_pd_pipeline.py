"""pd_scorecard and pd_challenger on a synthetic book: leakage, monotone constraints, shadow scoring."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ledger_core.pit import LeakageError
from ledger_models import pd as P
from ledger_models.train_pd import leakage_check
from ledger_scorecard.scorecard import Scaling

PROXIES = {"applicant_age", "applicant_zip5", "county_fips"}


def _book(n: int = 5000, seed: int = 3) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    frame = pl.DataFrame(
        {
            "application_id": [f"L{i:07d}" for i in range(n)],
            "application_date": [date(2023, 9, 1) + timedelta(days=int(d)) for d in rng.integers(0, 720, n)],
            "bureau_score": np.clip(np.round(700 - 45 * z + rng.normal(0, 25, n)), 300, 850).astype(int),
            "dti": np.clip(0.3 + 0.08 * z + rng.normal(0, 0.08, n), 0.01, 1.2),
            "revolving_utilization": np.clip(0.4 + 0.15 * z + rng.normal(0, 0.15, n), 0, 1),
            "delinquencies_24m": rng.poisson(np.exp(-1.5 + 0.5 * z)),
            "inquiries_6m": rng.poisson(1.0, n),
            "oldest_trade_months": rng.integers(6, 300, n),
            "employment_months": rng.integers(0, 240, n),
            "annual_income": np.round(rng.lognormal(np.log(60000), 0.4, n), -2),
            "loan_amount": np.round(rng.uniform(2000, 30000, n), -2),
            "term_months": rng.choice([36, 48, 60], n),
            "purpose": rng.choice(["auto", "debt_consolidation", "home_improvement"], n),
            "housing_status": rng.choice(["own", "rent", "mortgage"], n),
            "channel": rng.choice(["branch", "digital", "partner"], n),
            "applicant_age": rng.integers(21, 80, n),
        }
    )
    bad = (rng.random(n) < 1 / (1 + np.exp(-(-3.0 + 0.9 * z)))).astype(int)
    frame = frame.with_columns(bad=pl.Series(bad, dtype=pl.Int8))
    idx = (pl.col("application_date").dt.year() - 2023) * 12 + pl.col("application_date").dt.month() - 9
    return frame.with_columns(split=P.split_expr(idx), age_band=P.age_band_expr(pl.col("applicant_age")))


def _fit(book: pl.DataFrame) -> P.Fitted:
    return P.fit_all(
        book.filter(pl.col("split") == "development"),
        book.filter(pl.col("split") == "validation"),
        numeric=P.NUMERIC,
        categorical=P.CATEGORICAL,
        scaling=Scaling(600, 30, 20),
        cutoff=580,
        proxies=PROXIES,
        iv_floor=0.02,
        correlation_ceiling=0.7,
        min_bin_share=0.05,
        max_fine_bins=20,
        seed=1,
    )


@pytest.fixture(scope="module")
def fitted() -> tuple[pl.DataFrame, P.Fitted]:
    book = _book()
    return book, _fit(book)


def test_the_challenger_honours_its_monotone_constraints(fitted: tuple[pl.DataFrame, P.Fitted]) -> None:
    book, f = fitted
    assert f.constraints["bureau_score"] == -1 and f.constraints["revolving_utilization"] == 1
    row = book.head(1)
    for feature, sign in f.constraints.items():
        if sign == 0:
            continue
        lo, hi = float(book[feature].quantile(0.05)), float(book[feature].quantile(0.95))  # type: ignore[arg-type]
        grid = pl.concat(
            [
                row.with_columns(pl.lit(v).cast(book[feature].dtype).alias(feature))
                for v in np.linspace(lo, hi, 15)
            ]
        )
        preds = P.predict(f, grid, P.NUMERIC, P.CATEGORICAL)["challenger"]
        steps = np.diff(preds) * sign
        assert (steps >= -1e-12).all(), feature


def test_every_application_is_shadow_scored_by_both_models(fitted: tuple[pl.DataFrame, P.Fitted]) -> None:
    book, f = fitted
    preds = P.predict(f, book, P.NUMERIC, P.CATEGORICAL)
    assert preds["champion"].shape == preds["challenger"].shape == (book.height,)
    assert P.rank_agreement(preds["champion"], preds["challenger"]) > 0.7


def test_the_leakage_check_passes_on_the_application_record() -> None:
    book = _book(800)
    assert leakage_check(book, book) == 200


def test_the_leakage_check_catches_a_feature_updated_after_application() -> None:
    book = _book(800)
    leaked = book.with_columns(pl.col("bureau_score") + 25)
    with pytest.raises(LeakageError, match="bureau_score"):
        leakage_check(leaked, book)


def test_no_proxy_reaches_either_model(fitted: tuple[pl.DataFrame, P.Fitted]) -> None:
    _, f = fitted
    assert not {c.name for c in f.card.characteristics} & PROXIES
    assert not set(f.challenger_features) & PROXIES
