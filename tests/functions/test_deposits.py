"""Deposit betas: the recovery method, and the published betas against the generator's."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from ledger_bankgen.params import GeneratorParams
from ledger_core.manifest import Manifest
from ledger_functions.f06_deposits import BETA_TOLERANCE, offered_beta

ROOT = Path(__file__).resolve().parents[2]


def test_offered_beta_ignores_months_at_the_floor() -> None:
    policy = np.array([5.0, 4.0, 3.0, 2.0, 1.0, 0.5, 0.25, 0.1, 0.0])
    rate = np.maximum(0.25, 2.0 + 0.4 * (policy - 5.0))
    frame = pl.DataFrame({"policy_rate": policy, "savings_rate": rate})
    assert offered_beta(frame, "savings", 0.25) == pytest.approx(0.4)
    # Fitting through the floored months as well would understate the beta.
    assert offered_beta(frame, "savings", None) < 0.38


def test_published_betas_recover_the_generators_within_tolerance() -> None:
    # The generator's stated betas are code, so this runs on a fresh clone without the raw data.
    stated = GeneratorParams().betas
    manifest = Manifest.load(ROOT / "results" / "manifest.json")
    for product in ("checking", "savings", "time"):
        recovered = float(manifest.raw(f"f06.beta_{product}"))  # type: ignore[arg-type]
        assert abs(recovered - getattr(stated, product)) <= BETA_TOLERANCE, product
