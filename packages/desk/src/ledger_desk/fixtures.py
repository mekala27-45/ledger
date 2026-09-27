"""A small scored stream with known decisions, for the stream tests and the out of process check."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

DECLINES = (3, 11, 17, 29)
REVIEWS = (7, 23)


def sample_stream(n: int = 40) -> pl.DataFrame:
    """Transactions seven minutes apart, four declines and two reviews among them."""
    start = datetime(2026, 6, 1, 0, 5)
    decisions = ["approve"] * n
    for i in DECLINES:
        if i < n:
            decisions[i] = "decline"
    for i in REVIEWS:
        if i < n:
            decisions[i] = "review"
    return pl.DataFrame(
        {
            "txn_id": [900_000 + i for i in range(n)],
            "transaction_time": [start + timedelta(minutes=7 * i) for i in range(n)],
            "card_key": [f"K{(i % 5):010x}" for i in range(n)],
            "category": ["grocery_pos"] * n,
            "amount": [float(20 + i) for i in range(n)],
            "distance_km": [12.5] * n,
            "merchant_lat": [40.7] * n,
            "merchant_long": [-74.0] * n,
            "score": [0.9 if d == "decline" else 0.01 for d in decisions],
            "decision": decisions,
            "queue": [d == "decline" for d in decisions],
            "rule_new_category_large": [False] * n,
            "rule_burst": [d == "review" for d in decisions],
            "rule_distant_merchant": [False] * n,
            "model_reasons": ["large amount" if d != "approve" else "" for d in decisions],
            "is_fraud": [1 if d == "decline" else 0 for d in decisions],
        }
    ).with_columns(pl.col("transaction_time").cast(pl.Datetime("us")))
