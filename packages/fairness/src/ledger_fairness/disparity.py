"""Disparities in credit outcomes: unadjusted rate ratios and adjusted odds ratios.

Conventions used everywhere in this module:

* A ratio above one means the group is denied more often than its reference group.
* Unadjusted: the ratio of two denial rates, with the Katz log interval.
* Adjusted: the odds ratio on the group's indicator in a logistic regression of the
  denial on the controls the data allows, with lender fixed effects, so the group is
  compared with the reference group at the same lender with the same file.
* Every family of comparisons is corrected with Benjamini and Hochberg's procedure
  before anything is called a finding.

Nothing here is a finding of discrimination. An unadjusted gap can be explained by
legitimate differences in the files, and an adjusted gap can be produced by what the
public data leaves out (credit scores, the automated underwriting result). Examiners
look at both for exactly that reason.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy import stats

Z95 = 1.959963984540054


@dataclass(frozen=True)
class RateRatio:
    ratio: float
    low: float
    high: float
    p_value: float


def rate_ratio(events_group: int, n_group: int, events_ref: int, n_ref: int) -> RateRatio:
    """The ratio of the group's event rate to the reference's, with a 95% log interval."""
    if min(n_group, n_ref) <= 0:
        raise ValueError("a rate ratio needs applications in both groups")
    if events_group <= 0 or events_ref <= 0:
        raise ValueError("a rate ratio needs at least one event in each group")
    if events_group > n_group or events_ref > n_ref:
        raise ValueError("more events than applications")
    ratio = (events_group / n_group) / (events_ref / n_ref)
    se = math.sqrt(1 / events_group - 1 / n_group + 1 / events_ref - 1 / n_ref)
    z = math.log(ratio) / se if se > 0 else 0.0
    return RateRatio(
        ratio=ratio,
        low=math.exp(math.log(ratio) - Z95 * se),
        high=math.exp(math.log(ratio) + Z95 * se),
        p_value=float(2 * stats.norm.sf(abs(z))),
    )


def benjamini_hochberg(p_values: Sequence[float]) -> np.ndarray:
    """Benjamini and Hochberg adjusted p values for one family of comparisons."""
    p = np.asarray(p_values, dtype=float)
    if p.size == 0:
        raise ValueError("refusing to correct an empty family of comparisons")
    if np.any((p < 0) | (p > 1) | np.isnan(p)):
        raise ValueError("p values must lie in [0, 1]")
    n = p.size
    order = np.argsort(p)
    scaled = p[order] * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(scaled[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(adjusted, 0.0, 1.0)
    return out


def unadjusted_table(
    frame: pl.DataFrame, outcome: str, group: str, reference: str, min_applications: int = 100
) -> pl.DataFrame:
    """Applications, denials, the denial rate and the ratio to the reference, per group."""
    counts = (
        frame.group_by(group)
        .agg(pl.len().alias("applications"), pl.col(outcome).cast(pl.Int64).sum().alias("denials"))
        .filter(pl.col("applications") >= min_applications)
        .sort(group)
    )
    ref = counts.filter(pl.col(group) == reference)
    if ref.height != 1:
        raise ValueError(f"reference group {reference!r} is missing or too small")
    n_ref, d_ref = int(ref["applications"][0]), int(ref["denials"][0])
    rows = []
    for g, n, d in counts.select(group, "applications", "denials").iter_rows():
        if g == reference:
            rows.append(
                {
                    "group": g,
                    "applications": n,
                    "denials": d,
                    "rate": d / n,
                    "ratio": 1.0,
                    "low": None,
                    "high": None,
                    "p_value": None,
                }
            )
            continue
        r = rate_ratio(int(d), int(n), d_ref, n_ref)
        rows.append(
            {
                "group": g,
                "applications": n,
                "denials": d,
                "rate": d / n,
                "ratio": r.ratio,
                "low": r.low,
                "high": r.high,
                "p_value": r.p_value,
            }
        )
    return pl.DataFrame(rows, schema_overrides={"low": pl.Float64, "high": pl.Float64, "p_value": pl.Float64})


@dataclass(frozen=True)
class Design:
    """A model matrix with named columns, built without any protected attribute or proxy."""

    x: np.ndarray
    names: list[str]


def design_matrix(
    frame: pl.DataFrame,
    tested: dict[str, str],
    numeric: Sequence[str],
    categorical: Sequence[str],
    protected: set[str],
) -> Design:
    """Indicators for the tested groups (each against its reference), controls, an intercept.

    ``tested`` maps a protected attribute's column to its reference group; those are
    the only protected columns allowed in, because they are what is being measured.
    Any control that is a protected attribute or a listed proxy is refused.
    """
    controls = [c.lower() for c in (*numeric, *categorical)]
    leaked = sorted(set(controls) & protected)
    if leaked:
        raise ValueError(f"controls include protected attributes or proxies: {leaked}")
    cols: list[np.ndarray] = [np.ones(frame.height)]
    names = ["intercept"]
    for column, reference in tested.items():
        levels = sorted(v for v in frame[column].unique().to_list() if v is not None and v != reference)
        values = frame[column].to_numpy()
        for level in levels:
            cols.append((values == level).astype(float))
            names.append(f"{column}={level}")
    for column in numeric:
        cols.append(frame[column].cast(pl.Float64).to_numpy())
        names.append(column)
    for column in categorical:
        values = frame[column].cast(pl.Utf8).fill_null("missing").to_numpy()
        found, counts = np.unique(values, return_counts=True)
        baseline = found[int(np.argmax(counts))]
        for level in found:
            if level == baseline:
                continue
            cols.append((values == level).astype(float))
            names.append(f"{column}={level}")
    x = np.column_stack(cols)
    if np.isnan(x).any():
        raise ValueError("the design matrix has missing values; encode them before fitting")
    return Design(x, names)


def adjusted_odds_ratios(
    frame: pl.DataFrame,
    outcome: str,
    tested: dict[str, str],
    numeric: Sequence[str],
    categorical: Sequence[str],
    protected: set[str],
) -> tuple[pl.DataFrame, float]:
    """Odds ratios, intervals and p values on the tested groups' indicators, and the fit's pseudo R squared."""
    import statsmodels.api as sm

    design = design_matrix(frame, tested, numeric, categorical, protected)
    y = frame[outcome].cast(pl.Float64).to_numpy()
    if y.min() == y.max():
        raise ValueError("refusing to fit on a single outcome")
    fit = sm.Logit(y, design.x).fit(method="newton", maxiter=100, disp=False)
    _require_convergence(fit)
    rows = []
    for i, name in enumerate(design.names):
        column = name.split("=", 1)[0]
        if column not in tested:
            continue
        beta, se = float(fit.params[i]), float(fit.bse[i])
        rows.append(
            {
                "dimension": column,
                "group": name.split("=", 1)[1],
                "odds_ratio": math.exp(beta),
                "low": math.exp(beta - Z95 * se),
                "high": math.exp(beta + Z95 * se),
                "p_value": float(fit.pvalues[i]),
            }
        )
    return pl.DataFrame(rows), float(fit.prsquared)


def expected_rates(
    frame: pl.DataFrame, outcome: str, numeric: Sequence[str], categorical: Sequence[str], protected: set[str]
) -> np.ndarray:
    """Each application's denial probability from the controls alone, for observed to expected ratios."""
    import statsmodels.api as sm

    design = design_matrix(frame, {}, numeric, categorical, protected)
    y = frame[outcome].cast(pl.Float64).to_numpy()
    fit = sm.Logit(y, design.x).fit(method="newton", maxiter=100, disp=False)
    _require_convergence(fit)
    return np.asarray(fit.predict(design.x))


def _require_convergence(fit: object) -> None:
    """A fit that did not converge has no trustworthy interval; usually a level with no events."""
    retvals = getattr(fit, "mle_retvals", {}) or {}
    if not retvals.get("converged", False):
        raise ValueError(
            "the logistic fit did not converge; look for a category with no events or no non events"
        )
