"""The studio scores an applicant exactly as the API does.

When the API is asleep the studio scores in the browser from the published scorecard
file with web/src/app/studio/scorecard.ts. This scores the same applicants both ways,
including a value on a bin edge, a missing value and an unseen category, and requires
the same score, probability, decision, points and reasons.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest
from ledger_api.scoring import ScorecardService

ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "results" / "models" / "pd_scorecard" / "scorecard_generated.json"


def _applicants(card: dict) -> list[dict]:
    rng = random.Random(11)
    out: list[dict] = []
    for i in range(60):
        applicant: dict = {}
        for c in card["characteristics"]:
            bins = c["bins"]
            if c["kind"] == "categorical":
                cats = [cat for b in bins for cat in b["categories"]]
                applicant[c["name"]] = rng.choice(cats)
                continue
            b = rng.choice(bins)
            lo = b["lower"] if b["lower"] is not None else (b["upper"] - abs(b["upper"]) * 0.5 - 1)
            hi = b["upper"] if b["upper"] is not None else (b["lower"] + abs(b["lower"]) * 0.5 + 1)
            # Every fifth applicant sits exactly on a bin's upper edge, which belongs to that bin.
            applicant[c["name"]] = hi if i % 5 == 0 else round(rng.uniform(lo, hi), 4)
        out.append(applicant)
    edge = dict(out[0])
    first_numeric = next(c["name"] for c in card["characteristics"] if c["kind"] == "numeric")
    edge[first_numeric] = None
    out.append(edge)
    unseen = dict(out[1])
    categorical = [c["name"] for c in card["characteristics"] if c["kind"] == "categorical"]
    if categorical:
        unseen[categorical[0]] = "a_category_never_seen"
    out.append(unseen)
    return out


@pytest.mark.skipif(not CARD.exists(), reason="the scorecard has not been built")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_scoring_matches_the_api() -> None:
    card = json.loads(CARD.read_text())
    service = ScorecardService.load(ROOT / "results", ROOT / "rules")
    applicants = _applicants(card)
    script = (
        "const { scoreApplicant } = await import(process.argv[1]);"
        "const [card, reasons, applicants] = JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(applicants.map((a) => scoreApplicant(card, a, reasons))));"
    )
    payload = json.dumps([card, service.reasons, applicants])
    out = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--no-warnings",
            "--input-type=module",
            "-e",
            script,
            str(ROOT / "web" / "src" / "app" / "studio" / "scorecard.ts"),
            payload,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    browser = json.loads(out.stdout)
    declines = 0
    for applicant, b in zip(applicants, browser, strict=True):
        api = service.score(applicant)
        assert round(b["score"], 1) == api["score"], applicant
        assert round(b["probability"], 5) == api["probability_of_default"], applicant
        assert b["decision"] == api["decision"], applicant
        assert {k: round(v, 1) for k, v in b["points"].items()} == api["points"], applicant
        assert b["reasons"] == api["reasons"], applicant
        declines += api["decision"] == "decline"
    # The grid has to exercise the reasons, not only approvals.
    assert declines >= 5
