"""Fine classing, coarse classing toward monotone weight of evidence, and the bin table.

Conventions, stated once and used everywhere in this package:

* ``bad`` is the event (default), ``good`` is its absence.
* Weight of evidence for a bin is ln(share of all goods in the bin / share of all
  bads in the bin). A positive WoE is a bin safer than the population.
* Information value is the sum over bins of (good share minus bad share) times WoE,
  so every bin's contribution is non negative and the total is their sum.
* Missing values are a bin of their own, never merged into a neighbour and never
  part of the monotone ordering, because "missing" has no position on the scale.
* Counts are smoothed by half an observation when a bin has no goods or no bads, so
  WoE is always finite; the smoothing is visible in the bin table's counts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

SMOOTH = 0.5
MISSING = "missing"


@dataclass
class Bin:
    label: str
    lower: float | None = None  # numeric bins: lower < x <= upper; None means unbounded
    upper: float | None = None
    categories: tuple[str, ...] = ()
    goods: float = 0.0
    bads: float = 0.0
    is_missing: bool = False

    @property
    def count(self) -> float:
        return self.goods + self.bads

    def contains(self, value: object) -> bool:
        if self.is_missing:
            return value is None or (isinstance(value, float) and math.isnan(value))
        if self.categories:
            return str(value) in self.categories
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return False
        v = float(value)  # type: ignore[arg-type]
        above = self.lower is None or v > self.lower
        below = self.upper is None or v <= self.upper
        return above and below


@dataclass
class BinTable:
    characteristic: str
    kind: str  # "numeric" or "categorical"
    bins: list[Bin]
    direction: int = 0  # +1 WoE rises with the value, -1 falls, 0 categorical
    total_goods: float = field(init=False, default=0.0)
    total_bads: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.total_goods = sum(b.goods for b in self.bins)
        self.total_bads = sum(b.bads for b in self.bins)

    def woe(self) -> list[float]:
        return [woe_of(b.goods, b.bads, self.total_goods, self.total_bads) for b in self.bins]

    def iv_contributions(self) -> list[float]:
        out = []
        for b, w in zip(self.bins, self.woe(), strict=True):
            g, bd = _smoothed(b.goods, b.bads)
            out.append((g / self.total_goods - bd / self.total_bads) * w)
        return out

    def iv(self) -> float:
        return float(sum(self.iv_contributions()))

    def shares(self) -> list[float]:
        total = self.total_goods + self.total_bads
        return [b.count / total for b in self.bins]

    def bad_rates(self) -> list[float]:
        return [b.bads / b.count if b.count else float("nan") for b in self.bins]

    def ordered(self) -> list[Bin]:
        return [b for b in self.bins if not b.is_missing]

    def is_monotone(self) -> bool:
        if self.kind != "numeric":
            return True
        woes = [woe_of(b.goods, b.bads, self.total_goods, self.total_bads) for b in self.ordered()]
        rising = all(a <= b + 1e-12 for a, b in zip(woes, woes[1:], strict=False))
        falling = all(a >= b - 1e-12 for a, b in zip(woes, woes[1:], strict=False))
        return rising or falling

    def index_of(self, value: object) -> int:
        for i, b in enumerate(self.bins):
            if b.contains(value):
                return i
        # A category unseen in development falls into the riskiest bin, the conservative choice.
        woes = self.woe()
        return int(np.argmin(woes))


def _smoothed(goods: float, bads: float) -> tuple[float, float]:
    if goods == 0 or bads == 0:
        return goods + SMOOTH, bads + SMOOTH
    return goods, bads


def woe_of(goods: float, bads: float, total_goods: float, total_bads: float) -> float:
    g, b = _smoothed(goods, bads)
    return math.log((g / total_goods) / (b / total_bads))


def _numeric_edges(values: np.ndarray, max_bins: int) -> list[float]:
    qs = np.quantile(values, np.linspace(0, 1, max_bins + 1)[1:-1])
    edges = sorted({float(q) for q in qs})
    return edges


def fine_classing(
    values: np.ndarray, bad: np.ndarray, name: str, *, max_bins: int = 20, categorical: bool = False
) -> BinTable:
    """Initial bins: quantiles for numbers, one bin per level for categories."""
    if len(values) == 0:
        raise ValueError(f"refusing to bin {name}: no observations")
    if len(values) != len(bad):
        raise ValueError(f"{name}: values and outcomes differ in length")
    bad = bad.astype(float)
    if categorical:
        text = np.array(["" if v is None else str(v) for v in values], dtype=object)
        missing = np.array([v is None for v in values])
        bins: list[Bin] = []
        for level in sorted(set(text[~missing].tolist())):
            mask = (text == level) & ~missing
            bins.append(
                Bin(
                    label=level,
                    categories=(level,),
                    goods=float((1 - bad[mask]).sum()),
                    bads=float(bad[mask].sum()),
                )
            )
        if missing.any():
            bins.append(
                Bin(
                    label=MISSING,
                    is_missing=True,
                    goods=float((1 - bad[missing]).sum()),
                    bads=float(bad[missing].sum()),
                )
            )
        return BinTable(name, "categorical", bins)
    numeric = values.astype(float)
    missing = np.isnan(numeric)
    present = numeric[~missing]
    if present.size == 0:
        raise ValueError(f"refusing to bin {name}: every value is missing")
    edges = _numeric_edges(present, max_bins)
    bounds: list[float | None] = [None, *edges, None]
    bins = []
    for lo, hi in zip(bounds, bounds[1:], strict=False):
        mask = ~missing
        if lo is not None:
            mask &= numeric > lo
        if hi is not None:
            mask &= numeric <= hi
        if not mask.any():
            continue
        bins.append(
            Bin(label="", lower=lo, upper=hi, goods=float((1 - bad[mask]).sum()), bads=float(bad[mask].sum()))
        )
    if missing.any():
        bins.append(
            Bin(
                label=MISSING,
                is_missing=True,
                goods=float((1 - bad[missing]).sum()),
                bads=float(bad[missing].sum()),
            )
        )
    table = BinTable(name, "numeric", bins)
    _relabel(table)
    return table


def _merge(a: Bin, b: Bin) -> Bin:
    if a.categories or b.categories:
        cats = tuple(sorted(set(a.categories) | set(b.categories)))
        return Bin(label=", ".join(cats), categories=cats, goods=a.goods + b.goods, bads=a.bads + b.bads)
    return Bin(label="", lower=a.lower, upper=b.upper, goods=a.goods + b.goods, bads=a.bads + b.bads)


def _relabel(table: BinTable) -> None:
    for b in table.bins:
        if b.is_missing or b.categories:
            continue
        lo = "-inf" if b.lower is None else _fmt(b.lower)
        hi = "+inf" if b.upper is None else _fmt(b.upper)
        b.label = f"({lo}, {hi}]"


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.4g}"


def coarse_classing(table: BinTable, *, min_bin_share: float = 0.05) -> BinTable:
    """Merge bins until every bin holds its share and numeric WoE is monotone.

    Numeric: small bins merge with the neighbour whose bad rate is closest; then,
    while WoE is not monotone in the direction the data favours, the adjacent pair
    with the smallest WoE difference merges. Categorical: small levels merge into
    the level with the closest bad rate, and levels are then ordered by WoE.
    """
    total = table.total_goods + table.total_bads
    if total == 0:
        raise ValueError(f"refusing to coarse class {table.characteristic}: no observations")
    missing = [b for b in table.bins if b.is_missing]
    work = [b for b in table.bins if not b.is_missing]

    def rate(b: Bin) -> float:
        return b.bads / b.count if b.count else 0.0

    if table.kind == "numeric":
        while len(work) > 1:
            small = [i for i, b in enumerate(work) if b.count / total < min_bin_share]
            if not small:
                break
            i = min(small, key=lambda k: work[k].count)
            if i == 0:
                j = 1
            elif i == len(work) - 1:
                j = i - 1
            else:
                j = (
                    i - 1
                    if abs(rate(work[i - 1]) - rate(work[i])) <= abs(rate(work[i + 1]) - rate(work[i]))
                    else i + 1
                )
            lo, hi = sorted((i, j))
            work[lo : hi + 1] = [_merge(work[lo], work[hi])]
        present_goods = sum(b.goods for b in work)
        present_bads = sum(b.bads for b in work)
        xs = np.arange(len(work))
        woes = [woe_of(b.goods, b.bads, present_goods, present_bads) for b in work]
        direction = 1 if len(work) < 2 or np.corrcoef(xs, woes)[0, 1] >= 0 else -1
        while len(work) > 1:
            woes = [woe_of(b.goods, b.bads, present_goods, present_bads) for b in work]
            violations = [k for k in range(len(work) - 1) if (woes[k + 1] - woes[k]) * direction < 0]
            if not violations:
                break
            k = min(violations, key=lambda v: abs(woes[v + 1] - woes[v]))
            work[k : k + 2] = [_merge(work[k], work[k + 1])]
        out = BinTable(table.characteristic, "numeric", work + missing, direction=direction)
        _relabel(out)
        return out
    while len(work) > 1:
        small = [i for i, b in enumerate(work) if b.count / total < min_bin_share]
        if not small:
            break
        i = min(small, key=lambda k: work[k].count)
        others = [k for k in range(len(work)) if k != i]
        j = min(others, key=lambda k: abs(rate(work[k]) - rate(work[i])))
        merged = _merge(work[i], work[j])
        work = [b for k, b in enumerate(work) if k not in (i, j)] + [merged]
    goods = sum(b.goods for b in work) + sum(b.goods for b in missing)
    bads = sum(b.bads for b in work) + sum(b.bads for b in missing)
    work.sort(key=lambda b: woe_of(b.goods, b.bads, goods, bads))
    return BinTable(table.characteristic, "categorical", work + missing, direction=0)


def apply_bins(table: BinTable, values: np.ndarray) -> np.ndarray:
    """Index of the bin each value falls in."""
    return np.array([table.index_of(v) for v in values.tolist()], dtype=np.int32)


def woe_transform(table: BinTable, values: np.ndarray) -> np.ndarray:
    woes = np.array(table.woe(), dtype=float)
    out: np.ndarray = woes[apply_bins(table, values)]
    return out
