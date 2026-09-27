"""Net interest income under parallel rate shocks: repricing gaps, time weighted, with floors.

A position reprices some share of its balance within the horizon. A share that reprices
in month k earns (or pays) the shocked rate for the rest of the horizon, so its weight is
(horizon - k) / horizon. The change in net interest income over the horizon is then

    sum over assets of balance x weight x move  -  sum over liabilities of balance x weight x move

where a liability's move is its beta times the shock, and no rate falls below its floor.
It is a gap measure with a static balance sheet: balances are held flat, maturing money is
replaced at the new rate, and nothing about customer behaviour changes with the shock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Position:
    name: str
    side: Literal["asset", "liability"]
    balance: float
    weight: float  # time weighted share of the balance repricing within the horizon, 0 to 1
    beta: float = 1.0  # share of the shock passed through to this position's rate
    room_down: float | None = None  # percentage points the rate can fall before a floor

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"{self.name}: repricing weight {self.weight} is outside 0 to 1")
        if self.balance < 0:
            raise ValueError(f"{self.name}: negative balance")


def even_runoff_weight(share_in_horizon: float, horizon_months: int = 12) -> float:
    """Weight of a balance of which ``share_in_horizon`` runs off evenly across the horizon."""
    if not 0.0 <= share_in_horizon <= 1.0:
        raise ValueError("the share running off within the horizon must be between 0 and 1")
    months = range(1, horizon_months + 1)
    per_month = share_in_horizon / horizon_months
    return sum(per_month * (horizon_months - k) / horizon_months for k in months)


def maturity_weight(months_to_maturity: list[int], balances: list[float], horizon_months: int = 12) -> float:
    """Weight of a set of fixed rate items that reprice when they mature."""
    total = sum(balances)
    if total <= 0:
        return 0.0
    repriced = sum(
        b * (horizon_months - k) / horizon_months
        for k, b in zip(months_to_maturity, balances, strict=True)
        if 0 <= k < horizon_months
    )
    return repriced / total


def rate_move(position: Position, shock_bps: float) -> float:
    """The position's rate change in percentage points, after its beta and any floor."""
    move = position.beta * shock_bps / 100.0
    if move < 0 and position.room_down is not None:
        move = max(move, -position.room_down)
    return move


def nii_change(positions: list[Position], shock_bps: float) -> dict[str, float]:
    """The change in net interest income over the horizon, by position and in total, in dollars."""
    out: dict[str, float] = {}
    for p in positions:
        dollars = p.balance * p.weight * rate_move(p, shock_bps) / 100.0
        out[p.name] = dollars if p.side == "asset" else -dollars
    out["total"] = sum(out.values())
    return out
