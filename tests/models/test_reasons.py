"""Reasons read a flag the right way round."""

from __future__ import annotations

import numpy as np
from ledger_models.reasons import reasons

WORDS = {
    "digital": ("uses digital banking", "does not use digital banking"),
    "card": ("a card account", None),
    "balance": "balance",
}
NAMES = ["digital", "card", "balance"]


def test_an_absent_flag_is_named_as_absent() -> None:
    contrib = np.array([[0.9, 0.0, 0.1]])
    values = np.array([[0.0, 0.0, 5.0]])
    assert reasons(NAMES, contrib, values, WORDS) == ["does not use digital banking; balance"]


def test_a_flag_with_no_absent_wording_is_skipped_when_off() -> None:
    contrib = np.array([[0.0, -0.8, -0.2]])
    values = np.array([[1.0, 0.0, 5.0]])
    # Looking for what lowered the score: the card flag is off and has no absent words.
    assert reasons(NAMES, contrib, values, WORDS, direction=-1) == ["balance"]


def test_only_features_that_moved_the_score_the_asked_way_are_named() -> None:
    contrib = np.array([[-0.5, 0.0, -0.1]])
    values = np.array([[1.0, 1.0, 2.0]])
    assert reasons(NAMES, contrib, values, WORDS) == [""]
