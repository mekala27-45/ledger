"""The scorecard: variable selection, a logistic fit on WoE, points scaling and reason codes.

Scaling follows the convention every lender's scorecard documentation uses:

    factor = PDO / ln(2)
    offset = base_score - factor * ln(base_odds)
    score  = offset + factor * ln(odds of good)

With the logistic model fitted to the bad event on WoE inputs,
ln(odds of good) = -(b0 + sum_j b_j * WoE_j), so each characteristic's attribute
earns points = -(b_j * WoE_ij + b0 / n) * factor + offset / n, and the points add
up to the score exactly. The inverse turns any score back into a probability of
default, which is how the API and the studio report one.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression

from ledger_scorecard.binning import Bin, BinTable, coarse_classing, fine_classing, woe_transform


class ProxyError(ValueError):
    """A protected attribute or listed proxy was offered to a model."""


@dataclass(frozen=True)
class Scaling:
    base_score: float
    base_odds: float
    pdo: float

    @property
    def factor(self) -> float:
        return self.pdo / math.log(2)

    @property
    def offset(self) -> float:
        return self.base_score - self.factor * math.log(self.base_odds)

    def score_from_log_odds_good(self, log_odds_good: np.ndarray) -> np.ndarray:
        return self.offset + self.factor * log_odds_good

    def probability_of_bad(self, score: np.ndarray | float) -> np.ndarray:
        log_odds_good = (np.asarray(score, dtype=float) - self.offset) / self.factor
        return 1.0 / (1.0 + np.exp(log_odds_good))


@dataclass
class Characteristic:
    name: str
    table: BinTable
    coefficient: float
    points: list[float] = field(default_factory=list)

    @property
    def max_points(self) -> float:
        return max(self.points)


@dataclass
class Scorecard:
    characteristics: list[Characteristic]
    intercept: float
    scaling: Scaling
    cutoff: float
    target: str
    candidates: list[str]
    iv: dict[str, float]
    dropped: dict[str, str]

    def assign(self, frame: pl.DataFrame) -> np.ndarray:
        """Points per characteristic, one column per characteristic, in order."""
        cols = []
        for c in self.characteristics:
            idx = np.array([c.table.index_of(v) for v in frame[c.name].to_list()], dtype=np.int32)
            cols.append(np.asarray(c.points)[idx])
        return np.column_stack(cols) if cols else np.zeros((frame.height, 0))

    def score(self, frame: pl.DataFrame) -> np.ndarray:
        return self.assign(frame).sum(axis=1)

    def probability(self, frame: pl.DataFrame) -> np.ndarray:
        return self.scaling.probability_of_bad(self.score(frame))

    def logistic_probability(self, frame: pl.DataFrame) -> np.ndarray:
        """The fitted model's probability, straight from the WoE inputs, for the identity test."""
        z = np.full(frame.height, self.intercept)
        for c in self.characteristics:
            z = z + c.coefficient * woe_transform(c.table, frame[c.name].to_numpy())
        return 1.0 / (1.0 + np.exp(-z))

    def table(self) -> pl.DataFrame:
        rows = []
        for c in self.characteristics:
            for b, w, pts, share, br in zip(
                c.table.bins, c.table.woe(), c.points, c.table.shares(), c.table.bad_rates(), strict=True
            ):
                rows.append(
                    {
                        "characteristic": c.name,
                        "bin": b.label,
                        "share": share,
                        "bad_rate": br,
                        "woe": w,
                        "points": pts,
                        "iv": self.iv[c.name],
                    }
                )
        return pl.DataFrame(rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "intercept": self.intercept,
            "scaling": {
                "base_score": self.scaling.base_score,
                "base_odds": self.scaling.base_odds,
                "pdo": self.scaling.pdo,
                "factor": self.scaling.factor,
                "offset": self.scaling.offset,
            },
            "cutoff": self.cutoff,
            "candidates": self.candidates,
            "iv": self.iv,
            "dropped": self.dropped,
            "characteristics": [
                {
                    "name": c.name,
                    "kind": c.table.kind,
                    "direction": c.table.direction,
                    "coefficient": c.coefficient,
                    "bins": [
                        {
                            "label": b.label,
                            "lower": b.lower,
                            "upper": b.upper,
                            "categories": list(b.categories),
                            "missing": b.is_missing,
                            "goods": b.goods,
                            "bads": b.bads,
                            "woe": w,
                            "points": p,
                        }
                        for b, w, p in zip(c.table.bins, c.table.woe(), c.points, strict=True)
                    ],
                }
                for c in self.characteristics
            ],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1) + "\n", encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scorecard:
        s = data["scaling"]
        chars = []
        for c in data["characteristics"]:
            bins = [
                Bin(
                    label=b["label"],
                    lower=b["lower"],
                    upper=b["upper"],
                    categories=tuple(b["categories"]),
                    goods=b["goods"],
                    bads=b["bads"],
                    is_missing=b["missing"],
                )
                for b in c["bins"]
            ]
            table = BinTable(c["name"], c["kind"], bins, direction=c["direction"])
            chars.append(Characteristic(c["name"], table, c["coefficient"], [b["points"] for b in c["bins"]]))
        return cls(
            chars,
            data["intercept"],
            Scaling(s["base_score"], s["base_odds"], s["pdo"]),
            data["cutoff"],
            data["target"],
            data["candidates"],
            data["iv"],
            data["dropped"],
        )

    @classmethod
    def load(cls, path: Path) -> Scorecard:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def check_proxies(features: list[str], proxies: set[str]) -> None:
    hits = sorted(f for f in features if f.lower() in proxies)
    if hits:
        raise ProxyError(f"protected attributes or listed proxies offered as features: {hits}")


def fit_scorecard(
    frame: pl.DataFrame,
    target: str,
    candidates: list[str],
    *,
    categorical: set[str],
    scaling: Scaling,
    cutoff: float,
    proxies: set[str],
    iv_floor: float = 0.02,
    correlation_ceiling: float = 0.7,
    min_bin_share: float = 0.05,
    max_fine_bins: int = 20,
    manual_tables: dict[str, BinTable] | None = None,
) -> Scorecard:
    """Fine class, coarse class, select, fit, scale. Every step is its own tested function."""
    check_proxies(candidates, proxies)
    if frame.height == 0:
        raise ValueError("refusing to fit a scorecard on no rows")
    y = frame[target].to_numpy().astype(float)
    if y.min() == y.max():
        raise ValueError("refusing to fit a scorecard on a single outcome class")
    tables: dict[str, BinTable] = {}
    for name in candidates:
        if manual_tables and name in manual_tables:
            tables[name] = manual_tables[name]
            continue
        fine = fine_classing(
            frame[name].to_numpy(), y, name, max_bins=max_fine_bins, categorical=name in categorical
        )
        tables[name] = coarse_classing(fine, min_bin_share=min_bin_share)
    iv = {name: t.iv() for name, t in tables.items()}
    dropped: dict[str, str] = {}
    kept: list[str] = []
    woe_cols: dict[str, np.ndarray] = {}
    for name in sorted(candidates, key=lambda n: -iv[n]):
        if iv[name] < iv_floor:
            dropped[name] = f"information value {iv[name]:.4f} below the floor"
            continue
        col = woe_transform(tables[name], frame[name].to_numpy())
        if np.std(col) == 0:
            dropped[name] = "a single bin after coarse classing"
            continue
        clash = next(
            (k for k in kept if abs(float(np.corrcoef(col, woe_cols[k])[0, 1])) > correlation_ceiling), None
        )
        if clash is not None:
            dropped[name] = f"WoE correlation with {clash} above the ceiling"
            continue
        kept.append(name)
        woe_cols[name] = col
    if not kept:
        raise ValueError("no characteristic survived selection")
    x = np.column_stack([woe_cols[k] for k in kept])
    model = LogisticRegression(C=1e6, max_iter=5000)
    model.fit(x, y)
    coefs = model.coef_[0]
    # A characteristic whose coefficient has the wrong sign would give more points to the
    # riskier bins of a monotone characteristic; drop it and refit until none remain.
    while (coefs > 0).any() and len(kept) > 1:
        worst = kept[int(np.argmax(coefs))]
        dropped[worst] = "coefficient sign reversed in the joint fit"
        kept.remove(worst)
        x = np.column_stack([woe_cols[k] for k in kept])
        model = LogisticRegression(C=1e6, max_iter=5000)
        model.fit(x, y)
        coefs = model.coef_[0]
    intercept = float(model.intercept_[0])
    n = len(kept)
    chars = []
    for name, beta in zip(kept, coefs, strict=True):
        woes = np.array(tables[name].woe())
        points = -(beta * woes + intercept / n) * scaling.factor + scaling.offset / n
        chars.append(Characteristic(name, tables[name], float(beta), [float(p) for p in points]))
    return Scorecard(chars, intercept, scaling, cutoff, target, list(candidates), iv, dropped)


@dataclass(frozen=True)
class Reason:
    characteristic: str
    shortfall: float
    text: str


def adverse_action_reasons(
    card: Scorecard, row: pl.DataFrame, reason_text: dict[str, str], proxies: set[str], top: int = 4
) -> list[Reason]:
    """Reg B reasons: characteristics ranked by points below the maximum attainable.

    Returns nothing for an applicant at or above the cutoff. Never returns a
    protected attribute or listed proxy, and refuses a characteristic with no
    plain language reason on file.
    """
    if row.height != 1:
        raise ValueError("reasons are given for one applicant at a time")
    points = card.assign(row)[0]
    if points.sum() >= card.cutoff:
        return []
    shortfalls = []
    for c, got in zip(card.characteristics, points, strict=True):
        if c.name.lower() in proxies:
            raise ProxyError(f"{c.name} is a protected attribute or proxy and cannot be a reason")
        gap = c.max_points - float(got)
        if gap > 1e-9:
            if c.name not in reason_text:
                raise KeyError(f"no plain language reason on file for {c.name}")
            shortfalls.append(Reason(c.name, gap, reason_text[c.name]))
    shortfalls.sort(key=lambda r: -r.shortfall)
    return shortfalls[:top]


def psi(expected: np.ndarray, actual: np.ndarray, edges: np.ndarray | None = None, bins: int = 10) -> float:
    """Population stability index between two score distributions, on the expected deciles."""
    if expected.size == 0 or actual.size == 0:
        raise ValueError("refusing to compute stability on an empty population")
    if edges is None:
        edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)[1:-1]))
    e = np.bincount(np.searchsorted(edges, expected, side="right"), minlength=len(edges) + 1) / expected.size
    a = np.bincount(np.searchsorted(edges, actual, side="right"), minlength=len(edges) + 1) / actual.size
    e = np.clip(e, 1e-6, None)
    a = np.clip(a, 1e-6, None)
    return float(((a - e) * np.log(a / e)).sum())
