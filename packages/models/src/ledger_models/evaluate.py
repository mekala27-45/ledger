"""Discrimination, calibration, operating points and subgroup metrics, written plainly.

Every model reports the same measures so the inventory can compare them:
AUROC and Gini, the Kolmogorov Smirnov statistic, average precision, the Brier
score, expected calibration error over ten equal count bins, and a reliability
table. Thresholds are always chosen on one sample and reported on another; the
functions here take the threshold as an argument so they cannot choose it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


class EvaluationError(ValueError):
    pass


def _check(y: np.ndarray, p: np.ndarray) -> None:
    if y.size == 0:
        raise EvaluationError("refusing to evaluate on no rows")
    if y.size != p.size:
        raise EvaluationError("outcomes and scores differ in length")
    if y.min() == y.max():
        raise EvaluationError("refusing to evaluate discrimination with a single outcome class")


def auroc(y: np.ndarray, p: np.ndarray) -> float:
    _check(y, p)
    return float(roc_auc_score(y, p))


def ks_statistic(y: np.ndarray, p: np.ndarray) -> float:
    _check(y, p)
    order = np.argsort(p)
    ys = y[order]
    cum_bad = np.cumsum(ys) / ys.sum()
    cum_good = np.cumsum(1 - ys) / (1 - ys).sum()
    return float(np.max(np.abs(cum_bad - cum_good)))


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pl.DataFrame:
    """Equal count bins of predicted probability with observed rates."""
    if y.size == 0:
        raise EvaluationError("refusing to build a reliability table on no rows")
    order = np.argsort(p, kind="stable")
    groups = np.array_split(order, bins)
    rows = [
        {"bin": i + 1, "n": len(g), "predicted": float(p[g].mean()), "observed": float(y[g].mean())}
        for i, g in enumerate(groups)
        if len(g)
    ]
    return pl.DataFrame(rows)


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    table = reliability(y, p, bins)
    weights = table["n"].to_numpy() / table["n"].sum()
    gaps = np.abs(table["predicted"].to_numpy() - table["observed"].to_numpy())
    return float((weights * gaps).sum())


@dataclass(frozen=True)
class Discrimination:
    n: int
    events: int
    event_rate: float
    auroc: float
    gini: float
    ks: float
    average_precision: float
    brier: float
    ece: float


def discrimination(y: np.ndarray, p: np.ndarray) -> Discrimination:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    a = auroc(y, p)
    return Discrimination(
        n=int(y.size),
        events=int(y.sum()),
        event_rate=float(y.mean()),
        auroc=a,
        gini=2 * a - 1,
        ks=ks_statistic(y, p),
        average_precision=float(average_precision_score(y, p)),
        brier=float(brier_score_loss(y, p)),
        ece=ece(y, p),
    )


def confusion_at(y: np.ndarray, p: np.ndarray, threshold: float) -> dict[str, float]:
    flag = p >= threshold
    tp = float(((y == 1) & flag).sum())
    fp = float(((y == 0) & flag).sum())
    fn = float(((y == 1) & ~flag).sum())
    tn = float(((y == 0) & ~flag).sum())
    return {
        "threshold": threshold,
        "flagged": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / (tp + fn) if tp + fn else float("nan"),
        "fpr": fp / (fp + tn) if fp + tn else float("nan"),
    }


def subgroup_table(
    y: np.ndarray, p: np.ndarray, groups: np.ndarray, threshold: float | None = None
) -> pl.DataFrame:
    """Per group: size, event rate, mean score, AUROC where both classes exist, and rates at a threshold."""
    rows = []
    for g in sorted({str(x) for x in groups.tolist()}):
        mask = np.array([str(x) == g for x in groups.tolist()])
        yg, pg = y[mask], p[mask]
        row: dict[str, float | str | None] = {
            "group": g,
            "n": float(mask.sum()),
            "event_rate": float(yg.mean()) if yg.size else None,
            "mean_score": float(pg.mean()) if pg.size else None,
            "auroc": float(roc_auc_score(yg, pg)) if yg.size and 0 < yg.sum() < yg.size else None,
            "calibration_gap": float(pg.mean() - yg.mean()) if yg.size else None,
        }
        if threshold is not None and yg.size:
            c = confusion_at(yg, pg, threshold)
            row.update({"flag_rate": c["flagged"] / yg.size, "fpr": c["fpr"], "recall": c["recall"]})
        rows.append(row)
    return pl.DataFrame(rows)


def recall_at_fpr(y: np.ndarray, p: np.ndarray, target_fpr: float) -> tuple[float, float]:
    """The BAF suite's headline measure: recall at the threshold giving a fixed false positive rate.

    The threshold is the (1 - target_fpr) quantile of the negatives' scores.
    Returns (recall, threshold).
    """
    negatives = p[y == 0]
    if negatives.size == 0 or y.sum() == 0:
        raise EvaluationError("recall at a false positive rate needs both classes")
    threshold = float(np.quantile(negatives, 1 - target_fpr))
    recall = float((p[y == 1] >= threshold).mean())
    return recall, threshold


def bootstrap_auroc_interval(y: np.ndarray, p: np.ndarray, seed: int, reps: int = 200) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    values = []
    n = y.size
    for _ in range(reps):
        idx = rng.integers(0, n, n)
        if y[idx].min() == y[idx].max():
            continue
        values.append(roc_auc_score(y[idx], p[idx]))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
