"""The desk's replay worker: the scored test stream, played back in time order at a stated speed.

This is a replay, not a message bus. It reads a file of transactions the model has
already scored, advances a simulated clock (one simulated hour per real second by
default), and for every transaction the clock passes it pushes an event to every
subscriber and hands reviews and declines to a persistence callback. Precision and
recall on the live panel count only decisions whose chargeback window has closed by
the simulated clock; the panel always says how many decisions are still unlabelled.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl

Event = dict[str, Any]
AlertSink = Callable[[Event], Awaitable[None]]


def mask_card(card_key: str) -> str:
    return card_key[:3] + "*" * 5 + card_key[-3:]


def to_event(row: dict[str, Any], rule_statements: dict[str, str]) -> Event:
    rules = [rule_statements[k] for k in rule_statements if row.get(f"rule_{k}")]
    return {
        "txn_id": int(row["txn_id"]),
        "time": row["transaction_time"].isoformat(),
        "card": mask_card(str(row["card_key"])),
        "category": row["category"],
        "amount": round(float(row["amount"]), 2),
        "distance_km": round(float(row["distance_km"]), 1),
        "lat": round(float(row["merchant_lat"]), 3),
        "lon": round(float(row["merchant_long"]), 3),
        "score": round(float(row["score"]), 5),
        "decision": row["decision"],
        "queue": bool(row["queue"]),
        "rules": rules,
        "reasons": row.get("model_reasons") or "",
    }


@dataclass
class LabelBook:
    """Decisions and their eventual labels, to compute what the desk can know at a moment."""

    times: np.ndarray  # datetime64[us]
    declined: np.ndarray  # bool
    fraud: np.ndarray  # 0 or 1
    chargeback_days: int

    def at(self, clock: datetime) -> dict[str, Any]:
        seen = self.times <= np.datetime64(clock)
        labelled = seen & (self.times <= np.datetime64(clock - timedelta(days=self.chargeback_days)))
        y = self.fraud[labelled]
        d = self.declined[labelled]
        tp = int(((y == 1) & d).sum())
        return {
            "decisions": int(seen.sum()),
            "labelled": int(labelled.sum()),
            "unlabelled": int((seen & ~labelled).sum()),
            "precision": tp / int(d.sum()) if d.sum() else None,
            "recall": tp / int(y.sum()) if y.sum() else None,
        }


@dataclass
class ReplayWorker:
    stream: pl.DataFrame
    seconds_per_hour: float
    rule_statements: dict[str, str]
    labels: LabelBook
    on_alert: AlertSink | None = None
    loop_forever: bool = False
    # How far behind the simulated clock may fall before the replay treats it as a pause. A host
    # that freezes an idle instance and thaws it on the next request would otherwise find hours of
    # the stream overdue and send them in one burst.
    max_lag_seconds: float = 5.0
    subscribers: set[asyncio.Queue[Event]] = field(default_factory=set)
    emitted: int = 0
    counts: dict[str, int] = field(default_factory=lambda: {"approve": 0, "review": 0, "decline": 0})
    clock: datetime | None = None
    running: bool = False

    def __post_init__(self) -> None:
        if self.stream.height == 0:
            raise ValueError("refusing to replay an empty stream")
        self.stream = self.stream.sort("transaction_time", "txn_id")
        self._rows = self.stream.to_dicts()

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=5000)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self.subscribers.discard(queue)

    def snapshot(self) -> dict[str, Any]:
        total = sum(self.counts.values())
        panel = self.labels.at(self.clock) if self.clock else None
        return {
            "clock": self.clock.isoformat() if self.clock else None,
            "emitted": self.emitted,
            "rates": {k: (v / total if total else None) for k, v in self.counts.items()},
            "labelled": panel,
            "chargeback_days": self.labels.chargeback_days,
            "seconds_per_simulated_hour": self.seconds_per_hour,
        }

    async def _publish(self, event: Event) -> None:
        for queue in list(self.subscribers):
            if queue.full():
                # A subscriber that cannot keep up loses its oldest event, never blocks the desk.
                queue.get_nowait()
            queue.put_nowait(event)

    async def run(self, max_events: int | None = None) -> int:
        """Play the stream. With seconds_per_hour of zero the clock jumps straight to each event."""
        self.running = True
        try:
            while True:
                start_sim = self._rows[0]["transaction_time"]
                start_real = asyncio.get_running_loop().time()
                for row in self._rows:
                    due = row["transaction_time"]
                    if self.seconds_per_hour > 0:
                        wait = (due - start_sim).total_seconds() / 3600.0 * self.seconds_per_hour
                        delay = start_real + wait - asyncio.get_running_loop().time()
                        if delay > 0:
                            await asyncio.sleep(delay)
                        elif delay < -self.max_lag_seconds:
                            # Resume the replay from here instead of replaying the pause.
                            start_real -= delay
                    self.clock = due
                    event = to_event(row, self.rule_statements)
                    self.counts[event["decision"]] += 1
                    if event["decision"] != "approve" and self.on_alert is not None:
                        await self.on_alert(event)
                    event["panel"] = self.labels.at(due) if self.emitted % 50 == 0 else None
                    await self._publish(event)
                    self.emitted += 1
                    if max_events is not None and self.emitted >= max_events:
                        return self.emitted
                if not self.loop_forever:
                    return self.emitted
        finally:
            self.running = False
