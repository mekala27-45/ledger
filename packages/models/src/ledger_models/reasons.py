"""Reasons in plain words from per feature contributions, with binary features read the right way round.

A contribution says how far a feature moved one score from the average. For a flag that
is off, a positive contribution means its absence moved the score, so the reason has to
say "does not use digital banking", not "uses digital banking". A flag whose absence is
not a reason anyone would act on (a loan that is not a card) is given no absent wording
and is never shown when it is off.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

Words = str | tuple[str, str | None]


def reasons(
    names: Sequence[str],
    contributions: np.ndarray,
    values: np.ndarray,
    words: Mapping[str, Words],
    *,
    direction: int = 1,
    k: int = 2,
) -> list[str]:
    """For each row, the ``k`` features that moved the score most in ``direction``, in words.

    ``direction`` is 1 for features that raised the score and -1 for features that lowered it.
    A feature is binary when its words are a (present, absent) pair.
    """
    out: list[str] = []
    for contrib, row in zip(contributions, values, strict=True):
        picked: list[str] = []
        for j in np.argsort(-direction * contrib):
            if direction * contrib[j] <= 0 or len(picked) == k:
                break
            w = words[names[j]]
            if isinstance(w, tuple):
                text = w[0] if row[j] >= 0.5 else w[1]
                if text is None:
                    continue
            else:
                text = w
            if text not in picked:
                picked.append(text)
        out.append("; ".join(picked))
    return out
