"""The desk's operating point, its queue point, and precision that respects late labels.

The operating point is the score threshold that minimises expected cost on the
validation months: every genuine transaction declined costs the stated false
decline cost, and every fraud approved costs its amount plus the handling cost.
The queue point is the lowest threshold whose validation precision reaches the
stated floor, because an analyst's hour is budgeted. Both are chosen on
validation data and only ever reported on test data; the functions that choose
take validation arrays and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import polars as pl


@dataclass(frozen=True)
class CostPoint:
    threshold: float
    false_declines: int
    missed_frauds: int
    caught_frauds: int
    cost: float


def cost_at(
    y: np.ndarray, p: np.ndarray, amount: np.ndarray, threshold: float, c_fd: float, c_handle: float
) -> CostPoint:
    flag = p >= threshold
    fd = int(((y == 0) & flag).sum())
    missed = (y == 1) & ~flag
    cost = fd * c_fd + float((amount[missed] + c_handle).sum())
    return CostPoint(threshold, fd, int(missed.sum()), int(((y == 1) & flag).sum()), cost)


def candidate_thresholds(p: np.ndarray, n: int = 400) -> np.ndarray:
    qs = np.unique(np.quantile(p, np.linspace(0.5, 1.0, n)))
    return np.concatenate([qs, [1.0 + 1e-9]])


def cost_curve(
    y: np.ndarray,
    p: np.ndarray,
    amount: np.ndarray,
    c_fd: float,
    c_handle: float,
    thresholds: np.ndarray | None = None,
) -> pl.DataFrame:
    if y.size == 0:
        raise ValueError("refusing to draw a cost curve over no transactions")
    grid = candidate_thresholds(p) if thresholds is None else thresholds
    rows = []
    for t in grid:
        c = cost_at(y, p, amount, float(t), c_fd, c_handle)
        rows.append(
            {
                "threshold": c.threshold,
                "false_decline_cost": c.false_declines * c_fd,
                "missed_fraud_cost": c.cost - c.false_declines * c_fd,
                "total_cost": c.cost,
                "flagged": c.false_declines + c.caught_frauds,
            }
        )
    return pl.DataFrame(rows)


def choose_operating_point(
    y_val: np.ndarray, p_val: np.ndarray, amount_val: np.ndarray, c_fd: float, c_handle: float
) -> float:
    curve = cost_curve(y_val, p_val, amount_val, c_fd, c_handle)
    best = curve.sort(["total_cost", "threshold"]).row(0, named=True)
    return float(best["threshold"])


def choose_queue_point(
    y_val: np.ndarray, p_val: np.ndarray, precision_floor: float, operating_point: float
) -> float:
    """The lowest threshold whose precision on validation is at least the floor, never below the operating point.

    The queue is stricter than the decline: an analyst's action on a queued alert
    (blocking the card, calling the customer) is heavier than declining one
    transaction, so the queue can only narrow what the operating point flags.
    """
    order = np.argsort(-p_val)
    ys = y_val[order]
    ps = p_val[order]
    tp = np.cumsum(ys)
    precision = tp / np.arange(1, ys.size + 1)
    ok = np.flatnonzero(precision >= precision_floor)
    if ok.size == 0:
        raise ValueError("no threshold reaches the queue precision floor on validation")
    return max(float(ps[ok.max()]), operating_point)


def score_histogram(
    y: np.ndarray,
    p: np.ndarray,
    amount: np.ndarray,
    anchors: list[float],
    body_bins: int = 50,
    tail_bins: int = 150,
) -> pl.DataFrame:
    """Counts, frauds and fraud amounts by score bin, for a threshold slider that recomputes in a browser.

    Declines happen in the top percent of scores, so the bins are coarse below the
    99th percentile and fine above it. Every anchor (the operating point and the queue
    point) is a bin edge, so the slider set at an anchor flags exactly the transactions
    ``cost_at`` flags there and reproduces the reported precision and recall to the
    transaction. A bin holds scores from its lower edge up to, not including, the next.
    """
    if p.size == 0:
        raise ValueError("refusing to bin no scores")
    edges = np.unique(
        np.concatenate(
            [
                [0.0],
                np.quantile(p, np.linspace(0.5, 0.99, body_bins)),
                np.quantile(p, np.linspace(0.99, 1.0, tail_bins + 1)[:-1]),
                np.asarray(anchors, dtype=float),
                [1.0 + 1e-9],
            ]
        )
    )
    bins = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    frame = pl.DataFrame({"bin": bins, "fraud": y.astype(np.int64), "amount": amount.astype(float)})
    counts = frame.group_by("bin").agg(
        pl.len().alias("n"),
        pl.col("fraud").sum().alias("frauds"),
        (pl.col("fraud") * pl.col("amount")).sum().alias("fraud_amount"),
    )
    every = pl.DataFrame({"bin": np.arange(len(edges) - 1), "lower": edges[:-1]})
    return (
        every.join(counts, on="bin", how="left")
        .with_columns(
            pl.col("n").fill_null(0), pl.col("frauds").fill_null(0), pl.col("fraud_amount").fill_null(0.0)
        )
        .select("bin", "lower", "n", "frauds", "fraud_amount")
        .sort("bin")
    )


def accuracy_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """The threshold accuracy would choose, for the callout that explains why nobody should."""
    grid = candidate_thresholds(p)
    acc = [float(((p >= t) == (y == 1)).mean()) for t in grid]
    return float(grid[int(np.argmax(acc))])


def decide(score: np.ndarray, rules_fired: np.ndarray, operating_point: float) -> np.ndarray:
    """Decline at or above the operating point; review when only a rule fired; otherwise approve."""
    return np.where(score >= operating_point, "decline", np.where(rules_fired, "review", "approve"))


@dataclass(frozen=True)
class LabelledMetrics:
    as_of: datetime
    decisions: int
    labelled: int
    unlabelled: int
    precision: float | None
    recall: float | None


def labelled_metrics(
    times: np.ndarray, flagged: np.ndarray, is_fraud: np.ndarray, as_of: datetime, chargeback_days: int
) -> LabelledMetrics:
    """Precision and recall over decisions whose labels have arrived by ``as_of`` and nothing else.

    A transaction's label arrives chargeback_days after it. Anything newer is
    counted as unlabelled, never as genuine.
    """
    if times.size == 0:
        raise ValueError("refusing to compute desk metrics over no decisions")
    cutoff = np.datetime64(as_of - timedelta(days=chargeback_days))
    seen = times <= np.datetime64(as_of)
    labelled = seen & (times <= cutoff)
    y = is_fraud[labelled]
    f = flagged[labelled]
    tp = float(((y == 1) & f).sum())
    precision = tp / float(f.sum()) if f.sum() else None
    recall = tp / float(y.sum()) if y.sum() else None
    return LabelledMetrics(
        as_of, int(seen.sum()), int(labelled.sum()), int((seen & ~labelled).sum()), precision, recall
    )


def naive_precision(
    times: np.ndarray, flagged: np.ndarray, is_fraud_known: np.ndarray, as_of: datetime
) -> float | None:
    """The number a dashboard gets by treating every unlabelled decision as genuine. Never published as precision."""
    seen = times <= np.datetime64(as_of)
    f = flagged[seen]
    return float(((is_fraud_known[seen] == 1) & f).sum()) / float(f.sum()) if f.sum() else None


class DisjointnessError(AssertionError):
    """The sample that chose a threshold overlapped the sample it was reported on."""


def choose_on_validation_report_on_test(
    val_ids: np.ndarray,
    y_val: np.ndarray,
    p_val: np.ndarray,
    a_val: np.ndarray,
    test_ids: np.ndarray,
    y_test: np.ndarray,
    p_test: np.ndarray,
    a_test: np.ndarray,
    c_fd: float,
    c_handle: float,
) -> tuple[float, CostPoint, CostPoint]:
    """Choose the operating point on validation and cost it on test, refusing any overlap.

    Returns the threshold, the test cost at it, and the test cost of approving everything.
    """
    overlap = np.intersect1d(val_ids, test_ids)
    if overlap.size:
        raise DisjointnessError(
            f"{overlap.size} transactions are in both the choosing and the reporting sample"
        )
    threshold = choose_operating_point(y_val, p_val, a_val, c_fd, c_handle)
    at_threshold = cost_at(y_test, p_test, a_test, threshold, c_fd, c_handle)
    approve_all = cost_at(y_test, p_test, a_test, float("inf"), c_fd, c_handle)
    return threshold, at_threshold, approve_all


class LabelLeakError(AssertionError):
    """A desk figure counted decisions whose labels had not arrived."""


def check_labelled_only(metrics: LabelledMetrics, times: np.ndarray, chargeback_days: int) -> None:
    """Hold a published desk figure to the chargeback window."""
    cutoff = np.datetime64(metrics.as_of - timedelta(days=chargeback_days))
    allowed = int((times <= cutoff).sum())
    if metrics.labelled > allowed:
        raise LabelLeakError(
            f"{metrics.labelled - allowed} decisions inside the {chargeback_days} day window were counted as labelled"
        )
