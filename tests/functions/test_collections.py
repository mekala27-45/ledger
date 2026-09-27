"""The roll rate chain: rows sum to one, loans are conserved, and seasonality needs history."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ledger_functions.f09_collections import STATES, forecast, seasonal_factor, shift, transition_matrix

OPEN = ["current", "30", "60", "90+"]


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(OPEN), st.sampled_from(STATES), st.integers(0, 500)),
        min_size=1,
        max_size=40,
    )
)
def test_every_row_of_the_matrix_sums_to_one(flows: list[tuple[str, str, int]]) -> None:
    frame = pl.DataFrame(flows, schema=["from_state", "to_state", "loans"], orient="row")
    p = transition_matrix(frame)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert (p >= 0).all()
    for absorbing in ("charged_off", "paid_off"):
        i = STATES.index(absorbing)
        assert p[i, i] == 1.0


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.integers(0, 1000), min_size=4, max_size=4),
    st.lists(st.floats(0.5, 1.5), min_size=6, max_size=6),
)
def test_the_chain_conserves_loans(start_open: list[int], factors: list[float]) -> None:
    flows = pl.DataFrame(
        {
            "from_state": ["current", "current", "current", "30", "30", "60", "60", "90+", "90+"],
            "to_state": [
                "current",
                "30",
                "paid_off",
                "current",
                "60",
                "current",
                "90+",
                "90+",
                "charged_off",
            ],
            "loans": [900, 60, 40, 40, 60, 20, 80, 50, 50],
        }
    )
    p = transition_matrix(flows)
    start = np.array([*start_open, 0, 0], dtype=float)
    states, offs = forecast(start, p, factors)
    assert np.allclose(states.sum(axis=1), start.sum())
    assert (offs >= -1e-9).all()
    assert offs.sum() == pytest.approx(states[-1][STATES.index("charged_off")])


def test_seasonality_needs_a_year_of_history() -> None:
    rates = {"2024-01": 0.02, "2024-02": 0.04, "2024-03": 0.03}
    assert seasonal_factor(rates, "2024-04", 5) == 1.0
    assert seasonal_factor(rates, "2024-04", 2) == pytest.approx(0.04 / 0.03)
    assert shift("2024-11", 3) == "2025-02"
    assert shift("2024-01", -1) == "2023-12"


def test_months_between_counts_calendar_months() -> None:
    from ledger_functions.f09_collections import months_between

    assert months_between("2024-11", "2025-02") == 3
    assert months_between("2025-02", "2024-11") == -3
