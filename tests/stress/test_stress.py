"""Rate shocks, the macro link and the published stress paths."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from ledger_core.manifest import Manifest
from ledger_stress.link import fit_link, project, scenario_changes
from ledger_stress.nii import Position, even_runoff_weight, maturity_weight, nii_change, rate_move

ROOT = Path(__file__).resolve().parents[2]


def test_a_matched_book_moves_by_the_gap() -> None:
    book = [
        Position("loans", "asset", 100.0, 1.0),
        Position("deposits", "liability", 100.0, 1.0, beta=0.5),
    ]
    change = nii_change(book, 100)
    assert change["loans"] == pytest.approx(1.0)
    assert change["deposits"] == pytest.approx(-0.5)
    assert change["total"] == pytest.approx(0.5)
    assert nii_change(book, -100)["total"] == pytest.approx(-0.5)


def test_a_floor_stops_a_rate_falling() -> None:
    at_floor = Position("checking", "liability", 100.0, 1.0, beta=1.0, room_down=0.1)
    assert rate_move(at_floor, -100) == pytest.approx(-0.1)
    assert rate_move(at_floor, 100) == pytest.approx(1.0)
    # So a fall costs more than a rise earns when the deposit side is floored.
    book = [Position("cash", "asset", 100.0, 1.0), at_floor]
    assert nii_change(book, 100)["total"] == pytest.approx(0.0)
    assert nii_change(book, -100)["total"] == pytest.approx(-0.9)


def test_repricing_weights() -> None:
    assert even_runoff_weight(1.0, 12) == pytest.approx(66 / 144)
    assert even_runoff_weight(0.0, 12) == 0.0
    assert maturity_weight([0, 6, 12, 30], [1.0, 1.0, 1.0, 1.0], 12) == pytest.approx((1.0 + 0.5) / 4)
    with pytest.raises(ValueError):
        even_runoff_weight(1.5)
    with pytest.raises(ValueError):
        Position("bad", "asset", 1.0, 1.2)


def test_the_link_recovers_a_known_macro_sensitivity() -> None:
    rng = np.random.default_rng(11)
    rows = []
    for month in range(36):
        u = 1.0 + 2.5 * np.sin(month / 6) ** 2
        g = rng.normal(3, 2)
        for card in (0.0, 1.0):
            n = 20_000
            p = 1 / (1 + np.exp(-(-4.5 + 0.30 * u + 0.8 * card)))
            rows.append(
                {
                    "exposed": n,
                    "rolled": int(rng.binomial(n, p)),
                    "unemployment": u,
                    "hpi_growth": g,
                    "loose_vintage": float(month % 2),
                    "card": card,
                    "mob_6_11": float(month % 3 == 0),
                    "mob_12_23": float(month % 3 == 1),
                    "mob_24_plus": float(month % 5 == 0),
                }
            )
    # The other terms vary but carry no effect, so the design is full rank.
    fit = fit_link(pl.DataFrame(rows))
    low, high = fit.interval("unemployment")
    assert low < 0.30 < high
    assert abs(fit.coef("hpi_growth")) < 0.02


def test_a_worse_path_projects_a_higher_hazard() -> None:
    from ledger_stress.link import LinkFit

    fit = LinkFit(
        names=("const", "unemployment", "hpi_growth"),
        params=np.array([-4.0, 0.3, -0.01]),
        cov=np.diag([0.01, 0.0004, 0.0001]),
        n_cells=1,
        n_loan_months=1,
        events=1,
    )
    mild = project(0.01, np.array([0.0, 0.5, 1.0]), np.zeros(3), fit)
    severe = project(0.01, np.array([1.0, 3.0, 5.0]), np.zeros(3), fit)
    assert np.all(severe["central"] >= mild["central"])
    assert np.all(severe["low"] <= severe["central"]) and np.all(severe["central"] <= severe["high"])
    assert mild["central"][0] == pytest.approx(0.01)


def test_scenarios_are_applied_as_changes_from_their_jump_off() -> None:
    path = pl.DataFrame(
        {
            "quarter": ["2025Q4", "2026Q1", "2026Q2"],
            "unemployment_rate": [4.5, 6.0, 7.5],
            "house_price_index": [100.0, 99.0, 98.0],
        }
    )
    du, dh = scenario_changes(path, "2025Q4", ["2026Q1", "2026Q2"])
    assert du.tolist() == pytest.approx([1.5, 3.0])
    assert dh.shape == (2,)
    with pytest.raises(ValueError):
        scenario_changes(path, "2025Q4", ["2026Q1", "2026Q3"])


def test_published_paths_are_ordered_by_severity_and_the_link_recovers_the_generator() -> None:
    paths = pl.read_parquet(ROOT / "results" / "f08" / "stress_paths.parquet")
    base = paths.filter(pl.col("scenario") == "Baseline").sort("step")["roll_rate"].to_numpy()
    severe = paths.filter(pl.col("scenario") == "Severely adverse").sort("step")["roll_rate"].to_numpy()
    assert np.all(severe >= base)
    manifest = Manifest.load(ROOT / "results" / "manifest.json")
    recovered = float(manifest.raw("f08.link_unemployment"))  # type: ignore[arg-type]
    stated = float(manifest.raw("f08.link_stated"))  # type: ignore[arg-type]
    assert abs(recovered - stated) <= float(manifest.raw("f08.link_tolerance"))  # type: ignore[arg-type]
