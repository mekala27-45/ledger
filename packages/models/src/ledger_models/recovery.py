"""Known parameter recovery: the pipeline must find what the generator put in before anything is trusted.

The generator's default process, deposit pricing and recoveries are driven by
stated parameters (packages/bankgen params.py). Each is re-estimated here from the
warehouse the way an analyst would estimate it from a real book, using the truth
tables only where the estimate needs the latent risk score, and compared with the
stated value inside a stated tolerance. A miss stops the models stage.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import polars as pl
import statsmodels.api as sm
from scipy.stats import spearmanr


@dataclass(frozen=True)
class Recovered:
    parameter: str
    stated: float
    estimate: float
    low: float
    high: float
    tolerance: float
    method: str

    @property
    def within(self) -> bool:
        return abs(self.estimate - self.stated) <= self.tolerance


class RecoveryError(AssertionError):
    pass


def hazard_frame(con: duckdb.DuckDBPyConnection, truth_loans: pl.DataFrame) -> pl.DataFrame:
    """Installment loan months that start current, with whether they rolled to 30 days past due."""
    months = con.execute(
        """
        select f.loan_id, f.month, f.months_on_book, f.vintage, m.unemployment_rate,
            (f.state = 'dpd30')::int as rolled
        from marts.fct_loan_month as f
        join marts.dim_month as m using (month)
        where f.product = 'installment' and f.state_open = 'current'
            and f.state not in ('paid_off', 'matured')
        """
    ).pl()
    return months.join(truth_loans.select("loan_id", "latent_risk"), on="loan_id", how="inner")


def recover_default_process(
    frame: pl.DataFrame, loose_vintages: tuple[str, ...], seed: int, sample: int = 250_000
) -> dict[str, tuple[float, float, float]]:
    """Discrete time hazard: logit(roll) = a + b_risk z + b_macro (u - 4) + b_vintage loose + month on book effects."""
    if frame.height == 0:
        raise RecoveryError("no loan months to estimate the default process from")
    if frame.height > sample:
        # A fixed seed fixes the sample only if the rows arrive in a fixed order, and neither
        # a warehouse query nor a join promises one: sorted first, the estimate is the same
        # on every run instead of moving by a few hundredths.
        frame = frame.sort("loan_id", "month").sample(n=sample, seed=seed)
    mob = frame["months_on_book"].to_numpy()
    dummies = np.column_stack([(mob == k).astype(float) for k in range(1, int(mob.max()) + 1)])
    x = np.column_stack(
        [
            frame["latent_risk"].to_numpy(),
            frame["unemployment_rate"].to_numpy() - 4.0,
            frame["vintage"].is_in(list(loose_vintages)).to_numpy().astype(float),
            dummies,
        ]
    )
    x = sm.add_constant(x, has_constant="add")
    fit = sm.GLM(frame["rolled"].to_numpy(), x, family=sm.families.Binomial()).fit()
    ci = fit.conf_int()
    out = {}
    for name, col in (("beta_risk", 1), ("beta_macro", 2), ("vintage_effect", 3)):
        out[name] = (float(fit.params[col]), float(ci[col, 0]), float(ci[col, 1]))
    return out


def rank_order(con: duckdb.DuckDBPyConnection, truth_loans: pl.DataFrame, scores: pl.DataFrame) -> float:
    """Spearman correlation between the latent risk score and a model's predicted default probability."""
    joined = scores.join(truth_loans.select("loan_id", "latent_risk"), on="loan_id", how="inner")
    if joined.height < 30:
        raise RecoveryError("too few scored loans with a known latent score")
    rho = spearmanr(joined["latent_risk"].to_numpy(), joined["pd"].to_numpy()).statistic
    return float(rho)


def deposit_betas(
    con: duckdb.DuckDBPyConnection, floors: dict[str, float]
) -> dict[str, tuple[float, float, float]]:
    """Pass through of the policy rate to each product's rate, on months where no floor binds."""
    rates = con.execute(
        "select month, policy_rate, checking_rate, savings_rate, time_rate from staging.stg_deposit_rates order by month"
    ).pl()
    out = {}
    for product in ("checking", "savings", "time"):
        col = f"{product}_rate"
        free = rates.filter(pl.col(col) > floors[product] + 1e-9)
        if free.height < 6:
            raise RecoveryError(f"too few unfloored months to estimate the {product} beta")
        x = sm.add_constant(free["policy_rate"].to_numpy())
        fit = sm.OLS(free[col].to_numpy(), x).fit()
        lo, hi = fit.conf_int()[1]
        out[product] = (float(fit.params[1]), float(lo), float(hi))
    return out


def recovery_share(con: duckdb.DuckDBPyConnection, months: int = 24) -> float:
    """Cumulative recoveries as a share of charge offs at the stated horizon, installment loans."""
    row = con.execute(
        "select recovery_rate from marts.mart_recoveries where product = 'installment' and months_since = ?",
        [months],
    ).fetchone()
    if row is None or row[0] is None:
        raise RecoveryError(f"no installment charge offs have reached {months} months of recoveries")
    return float(row[0])


def table(results: list[Recovered]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "parameter": r.parameter,
                "stated": r.stated,
                "estimate": r.estimate,
                "interval_low": r.low,
                "interval_high": r.high,
                "tolerance": r.tolerance,
                "within": r.within,
                "method": r.method,
            }
            for r in results
        ]
    )
