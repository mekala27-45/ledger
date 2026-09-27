"""The macro link: the book's monthly roll into delinquency, as a function of the economy.

A binomial regression on loan month cells: the log odds of a current loan rolling thirty
days past due in a month, on unemployment, house price growth, the loose underwriting
vintages, months on book and the product. Fitted on the generated bank's thirty six
months, which include one recession quarter, so it is a short history with one stress
episode in it, and the report says so. The generator's macro sensitivity is a stated
parameter, and the fit has to recover it before a scenario path is projected.

A scenario is applied as changes from its own jump off point, added to the bank's own
starting conditions, because the bank's unemployment is not the nation's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
import statsmodels.api as sm

TERMS = ("unemployment", "hpi_growth", "loose_vintage", "card", "mob_6_11", "mob_12_23", "mob_24_plus")


@dataclass(frozen=True)
class LinkFit:
    names: tuple[str, ...]
    params: np.ndarray
    cov: np.ndarray
    n_cells: int
    n_loan_months: int
    events: int

    def coef(self, name: str) -> float:
        return float(self.params[self.names.index(name)])

    def interval(self, name: str, z: float = 1.959963984540054) -> tuple[float, float]:
        i = self.names.index(name)
        se = float(np.sqrt(self.cov[i, i]))
        return float(self.params[i] - z * se), float(self.params[i] + z * se)


def design(cells: pl.DataFrame) -> np.ndarray:
    x = cells.select(TERMS).to_numpy().astype(float)
    return np.column_stack([np.ones(len(x)), x])


def fit_link(cells: pl.DataFrame) -> LinkFit:
    """Grouped binomial GLM: ``rolled`` successes out of ``exposed`` in each cell.

    Unemployment is in percentage points above four; house price growth is annualised,
    in percentage points.
    """
    y = np.column_stack(
        [
            cells["rolled"].to_numpy().astype(float),
            (cells["exposed"] - cells["rolled"]).to_numpy().astype(float),
        ]
    )
    model = sm.GLM(y, design(cells), family=sm.families.Binomial())
    result = model.fit()
    if not result.converged:
        raise RuntimeError("the macro link did not converge")
    return LinkFit(
        names=("const", *TERMS),
        params=np.asarray(result.params),
        cov=np.asarray(result.cov_params()),
        n_cells=cells.height,
        n_loan_months=int(cells["exposed"].sum()),
        events=int(cells["rolled"].sum()),
    )


def logit(p: np.ndarray | float) -> np.ndarray:
    q = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.asarray(np.log(q / (1 - q)))


def expit(x: np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-x)))


def project(
    h0: float,
    d_unemployment: np.ndarray,
    d_hpi_growth: np.ndarray,
    fit: LinkFit,
    draws: int = 2000,
    seed: int = 7,
) -> dict[str, np.ndarray]:
    """Monthly roll hazard along a scenario path, shifted from today's hazard ``h0``.

    Returns the central path and the 5th and 95th percentiles over draws of the two macro
    coefficients from the fit's covariance.
    """
    iu, ih = fit.names.index("unemployment"), fit.names.index("hpi_growth")
    mean = fit.params[[iu, ih]]
    cov = fit.cov[np.ix_([iu, ih], [iu, ih])]
    rng = np.random.default_rng(seed)
    b = rng.multivariate_normal(mean, cov, size=draws)
    base = logit(h0)
    shift = np.outer(b[:, 0], d_unemployment) + np.outer(b[:, 1], d_hpi_growth)
    paths = expit(base + shift)
    central = expit(base + mean[0] * d_unemployment + mean[1] * d_hpi_growth)
    return {
        "central": central,
        "low": np.quantile(paths, 0.05, axis=0),
        "high": np.quantile(paths, 0.95, axis=0),
        "draws": paths,
    }


def scenario_changes(path: pl.DataFrame, jump_off: str, quarters: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Unemployment and annualised house price growth, as changes from the scenario's jump off quarter."""
    ordered = path.sort("quarter")
    hpi = ordered["house_price_index"].to_numpy()
    growth = np.concatenate([[np.nan], ((hpi[1:] / hpi[:-1]) ** 4 - 1) * 100])
    frame = ordered.with_columns(hpi_growth=pl.Series(growth))
    start = frame.filter(pl.col("quarter") == jump_off).row(0, named=True)
    picked = frame.filter(pl.col("quarter").is_in(quarters)).sort("quarter")
    if picked.height != len(quarters):
        raise ValueError("the scenario does not cover every projection quarter")
    du = picked["unemployment_rate"].to_numpy() - start["unemployment_rate"]
    dh = picked["hpi_growth"].to_numpy() - start["hpi_growth"]
    return np.asarray(du, dtype=float), np.asarray(dh, dtype=float)
