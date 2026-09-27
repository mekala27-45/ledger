"""Function 4: the fraud desk.

Question: at what score should the desk decline, what does that cost, and what can
the desk honestly say about its own precision this week? The model, the operating
point and the late label analysis are fraud_card's (see its validation report);
this module shapes them for the desk page: the cost curve, the precision recall
curve with both points marked, the label lag by day, the score histogram the
browser's threshold slider recomputes from, and a recorded replay of the stream
for when the live API is asleep.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest
from ledger_desk.operating import score_histogram
from ledger_desk.replay import LabelBook, to_event
from ledger_desk.rules import load_rules

from ledger_functions.base import Context, FunctionSpec

RECORDED_START = datetime(2026, 7, 14, 6, 0)
RECORDED_HOURS = 30


def run(ctx: Context) -> None:
    m = ctx.manifest
    folder = ctx.paths.models_dir / "fraud_card"
    fraud = Manifest.load(folder / "manifest.json")
    replayed: dict[str, Any] = {
        "backend": "replayed",
        "population": "Sparkov card transactions, June to August 2026",
        "source": "fraud_card scored stream",
    }
    cb = ctx.config.censoring.chargeback_window_days

    curve = pl.read_parquet(folder / "cost_curve.parquet")
    ctx.save("cost_curve", curve)
    pr = pl.read_parquet(folder / "pr_curve.parquet")
    ctx.save("pr_curve", pr)
    lag = pl.read_parquet(folder / "label_lag_daily.parquet")
    ctx.save("label_lag", lag)

    op = float(fraud.raw("models.fraud_card.operating_point"))  # type: ignore[arg-type]
    queue = float(fraud.raw("models.fraud_card.queue_point"))  # type: ignore[arg-type]
    test = pl.read_parquet(
        folder / "scored_stream.parquet", columns=["split", "score", "is_fraud", "amount"]
    ).filter(pl.col("split") == "test")
    hist = score_histogram(
        test["is_fraud"].to_numpy(), test["score"].to_numpy(), test["amount"].to_numpy(), [op, queue]
    )
    ctx.save("score_histogram", hist)
    m.put("f04.operating_point", op, "float4", **replayed)
    m.put("f04.queue_point", queue, "float4", **replayed)
    m.put_figure(
        "f04.fig_cost",
        "Expected cost of fraud by decline threshold, test months",
        f"False declines cost {fraud.text('models.fraud_card.cost_false_decline')} each and missed fraud costs its "
        f"amount plus {fraud.text('models.fraud_card.cost_handling')}. The threshold that minimised the sum on the "
        f"validation months, {format_value(op, 'float4')}, costs {fraud.text('models.fraud_card.cost_op')} on the "
        f"test months against {fraud.text('models.fraud_card.cost_all')} for approving everything. Accuracy would "
        f"have chosen {fraud.text('models.fraud_card.accuracy_point')} and cost {fraud.text('models.fraud_card.cost_acc')}.",
        data="f04/cost_curve.parquet",
        **replayed,
    )
    m.put_figure(
        "f04.fig_pr",
        "Precision and recall across thresholds, test months",
        f"At the operating point the desk declines with precision {fraud.text('models.fraud_card.precision_op')} and "
        f"recall {fraud.text('models.fraud_card.recall_op')}; the queue point narrows to precision "
        f"{fraud.text('models.fraud_card.precision_queue')} for the analyst queue.",
        data="f04/pr_curve.parquet",
        **replayed,
    )
    last = lag.sort("day").row(-1, named=True)
    m.put("f04.unlabelled_on_as_of", last["unlabelled"], "int", **replayed)
    m.put("f04.decisions_on_as_of", last["decisions"], "int", **replayed)
    m.put_figure(
        "f04.fig_lag",
        "What the desk could know, day by day",
        f"On {ctx.config.calendar.as_of.isoformat()}, {format_value(last['unlabelled'], 'int')} of "
        f"{format_value(last['decisions'], 'int')} scored decisions were still inside the {cb} day chargeback window. "
        f"Precision over the labelled ones was {format_value(last['precision_labelled'], 'pct1')}. A figure that "
        f"treated the unlabelled declines as mistakes would read {fraud.text('models.fraud_card.naive_precision_as_of')}.",
        data="f04/label_lag.parquet",
        **replayed,
    )

    # A recorded replay for the site: a stretch of the test stream in the live stream's event shape.
    stream = pl.read_parquet(folder / "replay_stream.parquet")
    history = pl.read_parquet(folder / "replay_history.parquet")
    book = pl.concat(
        [
            history,
            stream.select(
                "transaction_time", declined=pl.col("decision") == "decline", is_fraud=pl.col("is_fraud")
            ),
        ]
    ).sort("transaction_time")
    labels = LabelBook(
        book["transaction_time"].to_numpy(), book["declined"].to_numpy(), book["is_fraud"].to_numpy(), cb
    )
    rules = load_rules(ctx.paths.rules)
    window = stream.filter(
        (pl.col("transaction_time") >= RECORDED_START)
        & (pl.col("transaction_time") < RECORDED_START + timedelta(hours=RECORDED_HOURS))
    ).sort("transaction_time", "txn_id")
    events = [to_event(row, rules.statements) for row in window.to_dicts()]
    panels = []
    for hour in range(RECORDED_HOURS + 1):
        clock = RECORDED_START + timedelta(hours=hour)
        panels.append({"clock": clock.isoformat(), **labels.at(clock)})
    counts = window["decision"].value_counts().to_dicts()
    payload = {
        "recorded": True,
        "start": RECORDED_START.isoformat(),
        "hours": RECORDED_HOURS,
        "operating_point": op,
        "queue_point": queue,
        "chargeback_days": cb,
        "events": events,
        "panels": panels,
    }
    ctx.out.mkdir(parents=True, exist_ok=True)
    (ctx.out / "replay_recorded.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    m.put("f04.recorded_events", len(events), "int", **replayed)
    m.put("f04.recorded_hours", RECORDED_HOURS, "int", **replayed)
    m.put(
        "f04.recorded_declines",
        next((c["count"] for c in counts if c["decision"] == "decline"), 0),
        "int",
        **replayed,
    )


SPEC = FunctionSpec(
    code="f04",
    slug="desk",
    title="The fraud desk",
    question="At what score should the desk decline, what does that cost, and what can it honestly say about its precision this week?",
    run=run,
)
