"""Rules and rankings graded against the generator's injected truth, never against themselves.

An injected episode counts only if it posted: the generator drops entries that would
land on an account after it closed or in the last days of a month, and an episode
with nothing in the ledger is not something any monitoring system could find.
"""

from __future__ import annotations

import duckdb
import polars as pl

SLACK_DAYS = 1


def posted_truth(con: duckdb.DuckDBPyConnection, truth: pl.DataFrame) -> pl.DataFrame:
    """Injected episodes with at least one entry in the ledger, one row per episode and account.

    ``complete`` marks an episode whose every injected entry posted. Only complete
    episodes count toward recall: a round trip with a missing hop is not a round trip,
    and no rule should be blamed for not finding one.
    """
    posted = con.execute(
        """
        select reference as episode_id, count(*) as posted_entries
        from marts.fct_deposit_entry
        where reference is not null
        group by 1
        """
    ).pl()
    episodes = truth.group_by("episode_id").agg(
        pl.col("typology").first(),
        pl.col("n_entries").first().alias("injected_entries"),
        pl.len().alias("members"),
    )
    counts = episodes.join(posted, on="episode_id", how="inner").with_columns(
        # A trip around a ring is complete only when every member's hop posted, two legs each.
        complete=pl.when(pl.col("typology") == "round_tripping")
        .then(pl.col("posted_entries") >= 2 * pl.col("members"))
        .otherwise(pl.col("posted_entries") >= pl.col("injected_entries"))
    )
    return truth.join(
        counts.select("episode_id", "posted_entries", "injected_entries", "complete"),
        on="episode_id",
        how="inner",
    ).select(
        "episode_id",
        "typology",
        "start_at",
        "end_at",
        "ring_id",
        "account_id",
        "customer_id",
        "amount",
        "posted_entries",
        "injected_entries",
        "complete",
    )


def label_alerts(alerts: pl.DataFrame, truth: pl.DataFrame) -> pl.DataFrame:
    """Each alert's matching episode, if any: same account, same typology, overlapping in time."""
    if alerts.is_empty():
        raise ValueError("no alerts to label")
    slack = pl.duration(days=SLACK_DAYS)
    matched = (
        alerts.select("alert_id", "rule", "account_id", "start_at", "end_at")
        .join(
            truth.select(
                pl.col("episode_id"),
                pl.col("typology").alias("rule"),
                pl.col("account_id"),
                pl.col("start_at").alias("t_start"),
                pl.col("end_at").alias("t_end"),
            ),
            on=["rule", "account_id"],
            how="inner",
        )
        .filter(
            (pl.col("start_at") <= pl.col("t_end") + slack) & (pl.col("end_at") >= pl.col("t_start") - slack)
        )
        .group_by("alert_id")
        .agg(pl.col("episode_id").min())
    )
    return alerts.join(matched, on="alert_id", how="left").with_columns(
        true_positive=pl.col("episode_id").is_not_null()
    )


def scorecard(labelled: pl.DataFrame, truth: pl.DataFrame, transactions: int) -> pl.DataFrame:
    """Per typology: alerts, precision, episodes, recall, and alerts per hundred thousand transactions."""
    if transactions <= 0:
        raise ValueError("no transactions to scale the alert volume by")
    rows = []
    complete = truth.filter(pl.col("complete"))
    for rule in sorted(truth["typology"].unique().to_list()):
        a = labelled.filter(pl.col("rule") == rule)
        wanted = set(complete.filter(pl.col("typology") == rule)["episode_id"].to_list())
        episodes = len(wanted)
        found = len(wanted & set(a.filter(pl.col("true_positive"))["episode_id"].to_list()))
        partial = truth.filter((pl.col("typology") == rule) & ~pl.col("complete"))["episode_id"].n_unique()
        rows.append(
            {
                "rule": rule,
                "alerts": a.height,
                "true_positives": int(a["true_positive"].sum()),
                "precision": float(a["true_positive"].mean()) if a.height else None,  # type: ignore[arg-type]
                "episodes": episodes,
                "episodes_found": found,
                "partial_episodes": partial,
                "recall": found / episodes if episodes else None,
                "per_100k": a.height / transactions * 100_000,
            }
        )
    return pl.DataFrame(rows)
