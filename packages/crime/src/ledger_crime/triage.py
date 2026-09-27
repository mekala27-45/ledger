"""Features for alert triage, computed as of the moment each alert's window opened.

An investigator deciding which alert to open first knows the alert's own facts and
the account's history. The history features here use only entries strictly before
the alert window's start, so an alert never learns from its own activity twice and
never from anything after it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import duckdb
import numpy as np
import polars as pl

HISTORY_DAYS = 90
RULES = ("mule", "rapid_movement", "round_tripping", "structuring")
NUMERIC = (
    "log_amount",
    "entries",
    "counterparties",
    "branches",
    "log_tenure_days",
    "prior_cash_90d",
    "log_prior_inflow_90d",
    "amount_vs_monthly_inflow",
    "prior_alerts",
)
FEATURES = (*NUMERIC, *(f"rule_{r}" for r in RULES))


def history_features(con: duckdb.DuckDBPyConnection, alerts: pl.DataFrame) -> pl.DataFrame:
    """Each alert's account history over the days before its window: cash deposits and inflow."""
    keys = alerts.select("alert_id", "account_id", "start_at")
    con.register("alert_keys", keys.to_arrow())
    try:
        hist = con.execute(
            f"""
            select k.alert_id,
                count(e.entry_id) filter (where e.txn_type = 'CASH_DEPOSIT') as prior_cash_90d,
                coalesce(sum(e.amount::double) filter (where e.amount > 0), 0) as prior_inflow_90d
            from alert_keys k
            left join marts.fct_deposit_entry e
                on e.account_id = k.account_id
                and e.posted_at < k.start_at
                and e.posted_at >= k.start_at - interval {HISTORY_DAYS} day
            group by 1
            """
        ).pl()
        opened = con.execute(
            """
            select k.alert_id, a.open_date
            from alert_keys k left join marts.dim_deposit_account a on a.account_id = k.account_id
            """
        ).pl()
    finally:
        con.unregister("alert_keys")
    return hist.join(opened, on="alert_id", how="left")


def prior_alert_counts(alerts: pl.DataFrame) -> pl.DataFrame:
    """Alerts on the same account that had closed before this one's window opened."""
    pairs = alerts.select("alert_id", "account_id", "start_at").join(
        alerts.select(pl.col("account_id"), pl.col("end_at").alias("other_end")), on="account_id", how="left"
    )
    return pairs.group_by("alert_id").agg(
        (pl.col("other_end") < pl.col("start_at")).sum().cast(pl.Int64).alias("prior_alerts")
    )


def build_features(con: duckdb.DuckDBPyConnection, alerts: pl.DataFrame) -> pl.DataFrame:
    hist = history_features(con, alerts)
    prior = prior_alert_counts(alerts)
    frame = alerts.join(hist, on="alert_id", how="left").join(prior, on="alert_id", how="left")
    tenure = (pl.col("start_at").dt.date() - pl.col("open_date")).dt.total_days().clip(0, None)
    frame = frame.with_columns(
        log_amount=pl.col("amount").abs().log1p(),
        entries=pl.col("entries").cast(pl.Float64),
        counterparties=pl.col("counterparties").cast(pl.Float64),
        branches=pl.col("branches").cast(pl.Float64),
        log_tenure_days=tenure.cast(pl.Float64).log1p(),
        prior_cash_90d=pl.col("prior_cash_90d").cast(pl.Float64),
        log_prior_inflow_90d=pl.col("prior_inflow_90d").log1p(),
        amount_vs_monthly_inflow=pl.col("amount").abs() / (pl.col("prior_inflow_90d") / 3 + 100.0),
        prior_alerts=pl.col("prior_alerts").cast(pl.Float64),
        **{f"rule_{r}": (pl.col("rule") == r).cast(pl.Float64) for r in RULES},
    )
    missing = [c for c in FEATURES if frame[c].null_count()]
    if missing:
        raise ValueError(f"triage features with missing values: {missing}")
    return frame


def matrix(frame: pl.DataFrame) -> np.ndarray:
    return frame.select(FEATURES).to_numpy().astype(float)


def recompute_history(past: pl.DataFrame, row: Mapping[str, Any]) -> dict[str, float]:
    """The slow path for the leakage test: the history features from raw entries."""
    from datetime import timedelta

    start = row["start_at"] - timedelta(days=HISTORY_DAYS)
    window = past.filter(pl.col("posted_at") >= start)
    inflow = float(window.filter(pl.col("amount") > 0)["amount"].sum()) if window.height else 0.0
    cash = float(window.filter(pl.col("txn_type") == "CASH_DEPOSIT").height)
    return {"prior_cash_90d": cash, "log_prior_inflow_90d": float(np.log1p(inflow))}
