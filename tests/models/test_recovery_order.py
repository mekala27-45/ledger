"""The known parameter recovery gives the same estimate however its rows arrive.

The hazard fit samples loan months with a fixed seed. Before the rows were sorted, the
sample depended on the order the warehouse returned them in, and a rerun moved the
latent risk coefficient from 0.913 to 0.955 with nothing else changed.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from ledger_models.recovery import recover_default_process


def _loan_months(n_loans: int = 600, months: int = 12, seed: int = 3) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    loan = np.repeat(np.arange(n_loans), months)
    mob = np.tile(np.arange(1, months + 1), n_loans)
    risk = np.repeat(rng.normal(size=n_loans), months)
    unemployment = 4.0 + rng.normal(scale=0.5, size=loan.size)
    vintage = np.repeat(rng.choice(["2024-01", "2024-02", "2024-03"], size=n_loans), months)
    loose = np.isin(vintage, ["2024-02"]).astype(float)
    logit = -4.0 + 0.95 * risk + 0.3 * (unemployment - 4.0) + 0.45 * loose
    rolled = (rng.random(loan.size) < 1 / (1 + np.exp(-logit))).astype(int)
    return pl.DataFrame(
        {
            "loan_id": [f"L{i:05d}" for i in loan],
            "month": [f"2025-{m:02d}" for m in mob],
            "months_on_book": mob,
            "vintage": vintage,
            "unemployment_rate": unemployment,
            "rolled": rolled,
            "latent_risk": risk,
        }
    )


def test_the_estimate_does_not_depend_on_row_order() -> None:
    frame = _loan_months()
    shuffled = frame.sample(fraction=1.0, shuffle=True, seed=11)
    assert not frame.equals(shuffled)
    a = recover_default_process(frame, ("2024-02",), seed=7, sample=4_000)
    b = recover_default_process(shuffled, ("2024-02",), seed=7, sample=4_000)
    assert a == b


def test_the_sample_is_what_changes_the_estimate() -> None:
    # The same rows with a different seed give a different sample and a different estimate,
    # so the test above is not passing because sampling does nothing.
    frame = _loan_months()
    a = recover_default_process(frame, ("2024-02",), seed=7, sample=4_000)
    c = recover_default_process(frame, ("2024-02",), seed=8, sample=4_000)
    assert a["beta_risk"] != c["beta_risk"]
