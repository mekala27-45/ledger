"""Point in time features for card transactions: what the desk knew the instant the card was swiped.

Every feature for a transaction at time t uses only that card's or that
merchant's history strictly before t. Rolling windows are closed on the left, so
the transaction being scored never counts itself. The merchant's fraud rate uses
only labels that had arrived by t: a label arrives when the chargeback window has
elapsed after its transaction, so a merchant's fraud last week is invisible today.
``tests/desk/test_features.py`` recomputes 200 sampled rows from raw history.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import polars as pl

WINDOWS = {
    "10m": timedelta(minutes=10),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
MERCHANT_PRIOR_WEIGHT = 50.0

NUMERIC_FEATURES = [
    "amount",
    "log_amount",
    "hour",
    "weekday",
    "distance_km",
    "count_10m",
    "count_1h",
    "count_24h",
    "count_7d",
    "amount_1h",
    "amount_24h",
    "amount_7d",
    "seconds_since_last",
    "amount_vs_card_mean",
    "merchant_fraud_rate",
    "new_category",
    "km_from_last_merchant",
]
CATEGORICAL_FEATURES = ["category"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def haversine_km(lat1: pl.Expr, lon1: pl.Expr, lat2: pl.Expr, lon2: pl.Expr) -> pl.Expr:
    rad = math.pi / 180.0
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    a = (dlat / 2).sin().pow(2) + (lat1 * rad).cos() * (lat2 * rad).cos() * (dlon / 2).sin().pow(2)
    return 2 * 6371.0 * a.sqrt().arcsin()


def card_features(tx: pl.DataFrame) -> pl.DataFrame:
    """Velocity, recency and novelty per card, strictly from prior transactions."""
    if tx.height == 0:
        raise ValueError("refusing to build features for no transactions")
    frame = tx.sort("card_key", "transaction_time", "txn_id").with_columns(_one=pl.lit(1.0))
    exprs: list[pl.Expr] = []
    for name, window in WINDOWS.items():
        for source, prefix in (("amount", "amount"), ("_one", "count")):
            exprs.append(
                pl.col(source)
                .cast(pl.Float64)
                .rolling_sum_by("transaction_time", window_size=window, closed="left")
                .over("card_key")
                .fill_null(0.0)
                .alias(f"{prefix}_{name}")
            )
    frame = frame.with_columns(exprs).drop("_one")
    frame = frame.with_columns(
        seconds_since_last=(pl.col("transaction_time") - pl.col("transaction_time").shift(1).over("card_key"))
        .dt.total_seconds()
        .cast(pl.Float64),
        prior_count=pl.int_range(pl.len()).over("card_key").cast(pl.Float64),
        prior_sum=(pl.col("amount").cum_sum() - pl.col("amount")).over("card_key"),
        last_merchant_lat=pl.col("merchant_lat").shift(1).over("card_key"),
        last_merchant_long=pl.col("merchant_long").shift(1).over("card_key"),
        last_time=pl.col("transaction_time").shift(1).over("card_key"),
        seen_category=pl.int_range(pl.len()).over(["card_key", "category"]),
    )
    frame = frame.with_columns(
        amount_vs_card_mean=pl.when(pl.col("prior_count") > 0)
        .then(pl.col("amount") / (pl.col("prior_sum") / pl.col("prior_count")))
        .otherwise(None),
        new_category=((pl.col("seen_category") == 0) & (pl.col("prior_count") > 0)).cast(pl.Float64),
        km_from_last_merchant=haversine_km(
            pl.col("last_merchant_lat"),
            pl.col("last_merchant_long"),
            pl.col("merchant_lat"),
            pl.col("merchant_long"),
        ),
        minutes_since_last=(pl.col("seconds_since_last") / 60.0),
    )
    return frame.drop("prior_sum", "last_merchant_lat", "last_merchant_long", "seen_category")


def merchant_fraud_rate(tx: pl.DataFrame, chargeback_days: int, window_days: int = 90) -> pl.DataFrame:
    """Each transaction's merchant fraud rate from labels that arrived in the trailing window.

    A prior transaction's label arrives chargeback_days after it. Only labels that
    arrived in the ``window_days`` before the transaction count, so the feature
    means the same thing in the first month of the desk as in the twelfth; a
    cumulative count from the start of the data would grow with the calendar and
    teach the model that busy months are risky. The rate is smoothed toward the
    overall rate in the same window with a prior weight of 50 labels, so a
    merchant with three labelled transactions is not scored on three coin flips.
    """
    delay = timedelta(days=chargeback_days)
    window = timedelta(days=window_days)
    labels = (
        tx.select("merchant_key", "transaction_time", "is_fraud")
        .with_columns(arrives=pl.col("transaction_time") + delay)
        .sort("merchant_key", "arrives")
        .with_columns(
            labelled=pl.int_range(1, pl.len() + 1).over("merchant_key").cast(pl.Float64),
            frauds=pl.col("is_fraud").cast(pl.Float64).cum_sum().over("merchant_key"),
        )
        .select("merchant_key", "arrives", "labelled", "frauds")
        .sort("arrives")
    )
    overall = (
        tx.select("transaction_time", "is_fraud")
        .sort("transaction_time")
        .with_columns(arrives=pl.col("transaction_time") + delay)
        .with_columns(
            all_labelled=pl.int_range(1, pl.len() + 1).cast(pl.Float64),
            all_frauds=pl.col("is_fraud").cast(pl.Float64).cum_sum(),
        )
        .select("arrives", "all_labelled", "all_frauds")
    )
    # Strictly before: a label arriving at exactly the transaction's time is not yet known.
    probe = tx.select("txn_id", "merchant_key", "transaction_time").with_columns(
        now=pl.col("transaction_time") - pl.duration(microseconds=1),
        then=pl.col("transaction_time") - pl.duration(microseconds=1) - window,
    )

    def cumulative(at: str, suffix: str) -> pl.DataFrame:
        by_merchant = probe.sort(at).join_asof(
            labels,
            left_on=at,
            right_on="arrives",
            by="merchant_key",
            strategy="backward",
            check_sortedness=False,
        )
        both = by_merchant.sort(at).join_asof(overall, left_on=at, right_on="arrives", strategy="backward")
        return both.select(
            "txn_id",
            pl.col("labelled").fill_null(0.0).alias(f"labelled_{suffix}"),
            pl.col("frauds").fill_null(0.0).alias(f"frauds_{suffix}"),
            pl.col("all_labelled").fill_null(0.0).alias(f"all_labelled_{suffix}"),
            pl.col("all_frauds").fill_null(0.0).alias(f"all_frauds_{suffix}"),
        )

    joined = cumulative("now", "now").join(cumulative("then", "then"), on="txn_id")
    labelled = pl.col("labelled_now") - pl.col("labelled_then")
    frauds = pl.col("frauds_now") - pl.col("frauds_then")
    all_labelled = pl.col("all_labelled_now") - pl.col("all_labelled_then")
    all_frauds = pl.col("all_frauds_now") - pl.col("all_frauds_then")
    prior = pl.when(all_labelled > 0).then(all_frauds / all_labelled).otherwise(0.01)
    return joined.select(
        "txn_id",
        merchant_labelled=labelled,
        merchant_fraud_rate=(frauds + MERCHANT_PRIOR_WEIGHT * prior) / (labelled + MERCHANT_PRIOR_WEIGHT),
    )


def build(tx: pl.DataFrame, chargeback_days: int) -> pl.DataFrame:
    """The full feature table, one row per transaction, in time order."""
    base = tx.with_columns(
        hour=pl.col("transaction_time").dt.hour().cast(pl.Float64),
        weekday=pl.col("transaction_time").dt.weekday().cast(pl.Float64),
        log_amount=pl.col("amount").cast(pl.Float64).log1p(),
        amount=pl.col("amount").cast(pl.Float64),
        distance_km=haversine_km(
            pl.col("customer_lat"), pl.col("customer_long"), pl.col("merchant_lat"), pl.col("merchant_long")
        ),
    )
    feats = card_features(base)
    merchant = merchant_fraud_rate(base, chargeback_days)
    out = feats.join(merchant, on="txn_id", how="left").sort("transaction_time", "txn_id")
    return out


def recompute_row(history: pl.DataFrame, row: dict[str, object]) -> dict[str, float | None]:
    """The slow, obviously correct version of every card feature, for the leakage test."""
    t = row["transaction_time"]
    assert isinstance(t, datetime)
    past = history.filter(pl.col("transaction_time") < t)
    out: dict[str, float | None] = {}
    for name, window in WINDOWS.items():
        inside = past.filter(pl.col("transaction_time") >= t - window)
        out[f"count_{name}"] = float(inside.height)
        out[f"amount_{name}"] = float(inside["amount"].sum()) if inside.height else 0.0
    if past.height:
        last = past.sort("transaction_time").row(-1, named=True)
        out["seconds_since_last"] = (t - last["transaction_time"]).total_seconds()
        out["amount_vs_card_mean"] = float(row["amount"]) / float(np.mean(past["amount"].to_numpy()))  # type: ignore[arg-type]
        out["new_category"] = 0.0 if row["category"] in set(past["category"].to_list()) else 1.0
    else:
        out["seconds_since_last"] = None
        out["amount_vs_card_mean"] = None
        out["new_category"] = 0.0
    return out
