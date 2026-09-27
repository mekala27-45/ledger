"""Point in time features.

Every model states its prediction time. A feature for an entity at that time may
only use events strictly before it. ``PointInTimeFrame`` holds the event history
and answers "what did we know about this entity just before this moment", and
``recompute_check`` is the leakage test: it samples rows from a feature table built
by fast vectorised code and recomputes each one from the raw history the slow way.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl


class LeakageError(AssertionError):
    """A feature used information from at or after its prediction time."""


@dataclass(frozen=True)
class PointInTimeFrame:
    """Event history for many entities, sorted by entity then time."""

    frame: pl.DataFrame
    entity: str
    time: str

    @classmethod
    def build(cls, frame: pl.DataFrame, entity: str, time: str) -> PointInTimeFrame:
        missing = {entity, time} - set(frame.columns)
        if missing:
            raise KeyError(f"history is missing columns {sorted(missing)}")
        return cls(frame.sort([entity, time]), entity, time)

    def history_before(self, entity_id: Any, moment: datetime) -> pl.DataFrame:
        """Rows for one entity strictly before ``moment``. Ties are excluded on purpose."""
        return self.frame.filter((pl.col(self.entity) == entity_id) & (pl.col(self.time) < moment))

    def assert_features_before(
        self, features: pl.DataFrame, source_time_col: str, prediction_col: str
    ) -> None:
        """Fail if any feature row reports a source event at or after its prediction time."""
        bad = features.filter(pl.col(source_time_col) >= pl.col(prediction_col))
        if bad.height:
            raise LeakageError(f"{bad.height} feature rows used events at or after prediction time")


def recompute_check(
    features: pl.DataFrame,
    history: PointInTimeFrame,
    prediction_col: str,
    recompute: Callable[[pl.DataFrame, Mapping[str, Any]], Mapping[str, float]],
    columns: list[str],
    *,
    sample: int = 200,
    seed: int = 7,
    tolerance: float = 1e-6,
) -> int:
    """Recompute ``columns`` for sampled rows from raw history and compare.

    ``recompute`` receives the entity's history strictly before the prediction time
    and the feature row, and returns the expected values. Returns the number of rows
    checked; raises LeakageError on the first mismatch.
    """
    if features.height == 0:
        raise ValueError("recompute_check was handed an empty feature table")
    rng = np.random.default_rng(seed)
    take = min(sample, features.height)
    idx = rng.choice(features.height, size=take, replace=False)
    rows = features[np.sort(idx).tolist()].to_dicts()
    for row in rows:
        past = history.history_before(row[history.entity], row[prediction_col])
        expected = recompute(past, row)
        for col in columns:
            got = row[col]
            want = expected[col]
            if got is None and want is None:
                continue
            if (
                got is None
                or want is None
                or abs(float(got) - float(want)) > tolerance * max(1.0, abs(float(want)))
            ):
                raise LeakageError(
                    f"{col} for {row[history.entity]} at {row[prediction_col]}: pipeline {got}, recomputed {want}"
                )
    return take
