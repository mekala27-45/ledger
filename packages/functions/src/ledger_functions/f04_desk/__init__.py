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
    fairness(ctx, fraud)


def fairness(ctx: Context, card: Manifest) -> None:
    """The fairness audit beside the desk: the card model's, and application fraud under the BAF protocol."""
    m = ctx.manifest
    audit: dict[str, Any] = {
        "backend": "replayed",
        "population": "Sparkov card transactions, June to August 2026",
        "source": "fraud_card validation report",
    }
    rows = card.tables["models.fraud_card.subgroups"]
    col = {c: i for i, c in enumerate(rows.columns)}
    ages = [r for r in rows.rows if r[col["Group"]] not in ("F", "M")]
    high = max(ages, key=lambda r: float(r[col["Fpr"]] or 0))
    low = min(ages, key=lambda r: float(r[col["Fpr"]] or 0))
    m.put("f04.card_fpr_ratio_age", card.raw("models.fraud_card.fpr_ratio_age"), "float2", **audit)
    m.put_figure(
        "f04.fig_card_fairness",
        "Who the card model declines wrongly, by age band and gender",
        f"At the operating point, genuine transactions of cardholders {high[col['Group']]} are declined at "
        f"{format_value(high[col['Fpr']], 'pct2')} and those of cardholders {low[col['Group']]} at "
        f"{format_value(low[col['Fpr']], 'pct2')}, a ratio of "
        f"{format_value(card.raw('models.fraud_card.fpr_ratio_age'), 'float2')}. Sparkov generates age and gender, so "
        "they can be measured here; the model never sees either.",
        **audit,
    )

    account = Manifest.load(ctx.paths.models_dir / "fraud_account" / "manifest.json")
    k = "models.fraud_account"
    baf: dict[str, Any] = {
        "backend": "real:baf",
        "population": "Bank account applications in the BAF suite, base and variant II, 300,000 each",
        "source": "fraud_account validation report",
    }
    for key in (
        "recall_suite",
        "ratio",
        "fpr_older",
        "fpr_younger",
        "ii_recall_suite",
        "ii_ratio",
        "age_auc",
    ):
        entry = account.values[f"{k}.{key}"]
        m.put(f"f04.baf_{key}", entry.value, entry.fmt, **baf)
    m.put_figure(
        "f04.fig_baf",
        "Application fraud under the BAF suite's fairness protocol",
        f"At a {account.text(k + '.target_fpr')} false positive rate the model finds {account.text(k + '.recall_suite')} "
        f"of fraudulent applications in the base variant and {account.text(k + '.ii_recall_suite')} in variant II. "
        f"Genuine applicants aged {account.text(k + '.older_age')} and over are flagged at {account.text(k + '.fpr_older')} "
        f"against {account.text(k + '.fpr_younger')} for the rest, a predictive equality of {account.text(k + '.ratio')} "
        f"({account.text(k + '.ii_ratio')} in variant II), though the model never sees age.",
        **baf,
    )
    alternatives = account.tables[f"{k}.alternatives"]
    base_rows = [r for r in alternatives.rows if r[0] == "Base"]
    first, last = base_rows[0], base_rows[-1]
    m.put_figure(
        "f04.fig_alternatives",
        "What parity costs: the search for a less discriminatory alternative",
        f"The model's own features predict whether an applicant is {account.text(k + '.older_age')} or over with an "
        f"AUROC of {account.text(k + '.age_auc')}. Removing the strongest carriers of age one at a time moves the base "
        f"variant's predictive equality from {format_value(first[6], 'float2')} to {format_value(last[6], 'float2')} "
        f"and its recall from {format_value(first[3], 'pct1')} to {format_value(last[3], 'pct1')}. The model is kept "
        "and bounded to asking for documents, never to declining.",
        **baf,
    )


SPEC = FunctionSpec(
    code="f04",
    slug="desk",
    title="The fraud desk",
    question="At what score should the desk decline, what does that cost, and what can it honestly say about its precision this week?",
    run=run,
)
