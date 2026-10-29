"""Rebuild the desk's replay files from the staged card stream and the committed served model.

The API image replays `results/models/fraud_card/replay_stream.parquet` (the test months) and reads
`replay_history.parquet` (the validation months, for the labels the desk can know). Both are written
by the fraud card trainer, but retraining to get them would move the model: the fit depends on the
order of the rows, and a card stream regenerated on another machine orders transactions that share
a second differently (see DECISIONS.md, 2026-10-28). So this script scores the staged stream with the
committed model at its committed operating point and queue point, and writes the two files without
training anything.

`--check` then compares the rebuilt replay with what the site already publishes, and fails unless:

- the test months cost what the published manifest says at the operating point, with as many
  declines (the whole stream, not a sample);
- every event of the recorded replay in `web/public/data/f04/replay_recorded.json`, which was cut
  from the replay the model wrote when it was trained, appears in the rebuilt window with the same
  time, amount, category, distance, merchant location, score, decision, queue flag, rules and reasons;
- the cards of the two windows pair one to one. A regenerated stream can give a card another salted
  key, and transactions that share a second can swap ids; both are counted and reported, since the
  key is a label and the desk computes nothing from it.

    uv run --group sparkov python scripts/run_sparkov.py --customers 1250 --start 2025-09-01 --end 2026-08-31
    uv run ledger generate && uv run ledger contracts --generated-only   # stages the card stream
    git checkout -- results/contracts                                   # that run counts only the generated tables
    uv run python scripts/build_replay.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import polars as pl
from ledger_core.config import load_config
from ledger_core.paths import Paths
from ledger_desk import operating as O
from ledger_desk.replay import to_event
from ledger_desk.rules import load_rules
from ledger_desk.train import rebuild_replay

ROOT = Path(__file__).resolve().parents[1]
RECORDED = ROOT / "web" / "public" / "data" / "f04" / "replay_recorded.json"
FIELDS = ("time", "amount", "category", "distance_km", "lat", "lon")
CONTENT = ("score", "decision", "queue", "rules", "reasons")


def _key(event: dict[str, object]) -> tuple[object, ...]:
    return tuple(event[f] for f in FIELDS)


def _content(event: dict[str, object]) -> tuple[object, ...]:
    return tuple(tuple(event[f]) if f == "rules" else event[f] for f in CONTENT)  # type: ignore[arg-type]


def check(paths: Paths) -> dict[str, object]:
    folder = paths.models_dir / "fraud_card"
    stream = pl.read_parquet(folder / "replay_stream.parquet")
    serving = json.loads((folder / "serving.json").read_text())
    cfg = load_config(paths.config)
    cost = O.cost_at(
        stream["is_fraud"].to_numpy().astype(float),
        stream["score"].to_numpy(),
        stream["amount"].to_numpy(),
        float(serving["operating_point"]),
        cfg.fraud_desk.cost_false_decline,
        cfg.fraud_desk.cost_missed_fraud_handling,
    )
    values = json.loads((folder / "manifest.json").read_text())["values"]
    published_cost = float(values["models.fraud_card.cost_op"]["value"])
    published_flagged = int(values["models.fraud_card.flagged_op"]["value"])
    flagged = cost.false_declines + cost.caught_frauds

    recorded = json.loads(RECORDED.read_text())
    start = datetime.fromisoformat(recorded["start"])
    rules = load_rules(paths.rules)
    window = stream.filter(
        (pl.col("transaction_time") >= start)
        & (pl.col("transaction_time") < start + pl.duration(hours=int(recorded["hours"])))
    ).sort("transaction_time", "txn_id")
    rebuilt = [to_event(row, rules.statements) for row in window.to_dicts()]
    by_key: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for e in rebuilt:
        by_key[_key(e)].append(e)
    agree = 0
    pairs: dict[str, set[str]] = defaultdict(set)
    for e in recorded["events"]:
        match = next((c for c in by_key.get(_key(e), []) if _content(c) == _content(e)), None)
        if match is not None:
            by_key[_key(e)].remove(match)
            agree += 1
            pairs[str(e["card"])].add(str(match["card"]))
    inverse: dict[str, set[str]] = defaultdict(set)
    for card, others in pairs.items():
        for other in others:
            inverse[other].add(card)
    ids = {e["txn_id"]: _key(e) for e in rebuilt}
    return {
        "test_transactions": stream.height,
        "test_frauds": int(stream["is_fraud"].sum()),
        "cost_at_operating_point": round(cost.cost, 2),
        "published_cost": published_cost,
        "declines_at_operating_point": flagged,
        "published_declines": published_flagged,
        "recorded_events": len(recorded["events"]),
        "rebuilt_events_in_window": len(rebuilt),
        "agree_on_everything_but_the_card_key": agree,
        "cards_in_window": len(pairs),
        "cards_paired_one_to_one": all(len(v) == 1 for v in pairs.values())
        and all(len(v) == 1 for v in inverse.values()),
        "cards_with_the_same_key": sum(1 for card, others in pairs.items() if card in others),
        "events_with_the_same_transaction_id": sum(
            1 for e in recorded["events"] if ids.get(e["txn_id"]) == _key(e)
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with what the site publishes")
    args = parser.parse_args(argv)
    paths = Paths(ROOT)
    staged = paths.staged / "sparkov" / "card_transactions.parquet"
    if not staged.exists():
        print(f"no staged card stream at {staged}; run the Sparkov wrapper and the card contracts first")
        return 2
    counts = rebuild_replay(paths.root, load_config(paths.config), paths.models_dir)
    print(json.dumps({"rows": counts}))
    if not args.check:
        return 0
    result = check(paths)
    print(json.dumps(result, indent=1))
    reproduced = (
        abs(float(result["cost_at_operating_point"]) - float(result["published_cost"])) < 0.005  # type: ignore[arg-type]
        and result["declines_at_operating_point"] == result["published_declines"]
        and result["agree_on_everything_but_the_card_key"] == result["recorded_events"]
        and result["rebuilt_events_in_window"] == result["recorded_events"]
        and result["cards_paired_one_to_one"] is True
    )
    if not reproduced:
        print("the rebuilt replay does not reproduce what the site publishes; do not commit it")
        return 1
    print("the rebuilt replay reproduces the published desk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
