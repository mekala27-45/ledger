"""attrition: the split respects the twelve month outcome, and the list counts money as well as people."""

from __future__ import annotations

import numpy as np
from ledger_models.train_attrition import TEST, TRAIN, VALIDATION, capture, outcomes_known_before


def test_every_fitting_outcome_was_known_before_the_test_months() -> None:
    assert outcomes_known_before(TRAIN[1], TEST[0])
    assert outcomes_known_before(VALIDATION[1], TEST[0])


def test_the_first_split_is_rejected() -> None:
    # Month ends up to December 2024 have outcomes running to December 2025, after the
    # summer 2025 test month ends; the challenge in DECISIONS.md replaced that split.
    assert not outcomes_known_before("2024-12", "2025-06")
    # Exactly twelve months apart is the earliest a month end's outcome may be used.
    assert outcomes_known_before("2024-06", "2025-06")
    assert not outcomes_known_before("2024-07", "2025-06")


def test_capture_counts_closers_and_their_balances() -> None:
    y = np.array([1, 0, 0, 0, 1, 0, 0, 0, 0, 1], dtype=float)
    money = np.array([100.0, 5, 5, 5, 10, 5, 5, 5, 5, 1000])
    by_probability = np.array([0.9, 0.1, 0.1, 0.1, 0.8, 0.1, 0.1, 0.1, 0.1, 0.2])
    # The top fifth by probability holds two of three closers but little of their money.
    found, share = capture(y, by_probability, money, 0.2)
    assert found == 2 / 3
    assert share == 110 / 1110
    # Ranked by expected balance at risk, the big closer comes first.
    found, share = capture(y, by_probability * money, money, 0.2)
    assert found == 2 / 3
    assert share == 1100 / 1110
