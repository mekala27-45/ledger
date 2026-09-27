"""The models the API serves, loaded once from results/models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import polars as pl
from ledger_scorecard.policy_files import load_proxies, load_reason_codes
from ledger_scorecard.scorecard import Scorecard, adverse_action_reasons


def digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass
class ScorecardService:
    card: Scorecard
    reasons: dict[str, str]
    proxies: set[str]
    top: int

    @classmethod
    def load(cls, results: Path, rules: Path, top: int = 4) -> ScorecardService:
        card = Scorecard.load(results / "models" / "pd_scorecard" / "scorecard_generated.json")
        return cls(card, load_reason_codes(rules, "generated"), load_proxies(rules), top)

    def characteristics(self) -> list[str]:
        return [c.name for c in self.card.characteristics]

    def score(self, applicant: dict[str, Any]) -> dict[str, Any]:
        offered = {k.lower() for k in applicant}
        blocked = sorted(offered & self.proxies)
        if blocked:
            raise ValueError(f"protected attributes or proxies cannot be scored: {blocked}")
        missing = [c for c in self.characteristics() if c not in applicant]
        if missing:
            raise ValueError(f"missing characteristics: {missing}")
        row = pl.DataFrame({c: [applicant[c]] for c in self.characteristics()})
        points = self.card.assign(row)[0]
        score = float(points.sum())
        probability = float(self.card.scaling.probability_of_bad(score))
        reasons = adverse_action_reasons(self.card, row, self.reasons, self.proxies, top=self.top)
        return {
            "score": round(score, 1),
            "probability_of_default": round(probability, 5),
            "cutoff": self.card.cutoff,
            "decision": "approve" if score >= self.card.cutoff else "decline",
            "points": {
                c.name: round(float(p), 1) for c, p in zip(self.card.characteristics, points, strict=True)
            },
            "reasons": [r.text for r in reasons],
        }


@dataclass
class FraudService:
    booster: lgb.Booster
    features: list[str]
    levels: list[str]
    operating_point: float
    queue_point: float

    @classmethod
    def load(cls, results: Path) -> FraudService:
        folder = results / "models" / "fraud_card"
        meta = json.loads((folder / "serving.json").read_text())
        booster = lgb.Booster(model_file=str(folder / "model.txt"))
        return cls(
            booster, meta["features"], meta["category_levels"], meta["operating_point"], meta["queue_point"]
        )

    def score(self, features: dict[str, Any]) -> dict[str, Any]:
        missing = [f for f in self.features if f not in features]
        if missing:
            raise ValueError(f"missing point in time features: {missing}")
        mapping = {v: float(i) for i, v in enumerate(self.levels)}
        row = [
            float(features[f]) if f != "category" else mapping.get(str(features[f]), np.nan)
            for f in self.features
        ]
        probability = float(self.booster.predict(np.array([row], dtype=float))[0])
        decision = "decline" if probability >= self.operating_point else "approve"
        return {
            "score": round(probability, 6),
            "operating_point": self.operating_point,
            "queue_point": self.queue_point,
            "decision": decision,
            "queue": probability >= self.queue_point,
        }
