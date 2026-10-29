"""The desk: point in time features, the label delay, rules, the operating point and the replay."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ledger_core.pit import LeakageError, PointInTimeFrame, recompute_check
from ledger_desk import features as F
from ledger_desk import operating as O
from ledger_desk.replay import LabelBook, ReplayWorker, mask_card
from ledger_desk.rules import load_rules, rule_columns

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = ["grocery_pos", "gas_transport", "shopping_net", "travel"]


def _stream(n: int = 3000, cards: int = 40, seed: int = 5) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2025, 9, 1)
    times = sorted(start + timedelta(seconds=int(s)) for s in rng.integers(0, 200 * 86400, n))
    return pl.DataFrame(
        {
            "txn_id": np.arange(1, n + 1),
            "card_key": [f"K{c:010x}" for c in rng.integers(0, cards, n)],
            "transaction_time": times,
            "category": rng.choice(CATEGORIES, n),
            "amount": np.round(rng.lognormal(3.5, 1.0, n), 2),
            "merchant_key": [f"M{m:08x}" for m in rng.integers(0, 30, n)],
            "merchant_lat": rng.uniform(40, 41, n),
            "merchant_long": rng.uniform(-75, -74, n),
            "customer_lat": np.full(n, 40.5),
            "customer_long": np.full(n, -74.5),
            "is_fraud": (rng.random(n) < 0.05).astype(np.int8),
        }
    ).with_columns(pl.col("transaction_time").cast(pl.Datetime("us")))


@pytest.fixture(scope="module")
def built() -> tuple[pl.DataFrame, pl.DataFrame]:
    tx = _stream()
    return tx, F.build(tx, 60)


def test_card_features_recompute_from_raw_history(built: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    tx, feats = built
    history = PointInTimeFrame.build(
        tx.select("card_key", "transaction_time", "amount", "category"), "card_key", "transaction_time"
    )
    columns = [
        "count_10m",
        "count_1h",
        "count_24h",
        "count_7d",
        "amount_1h",
        "amount_24h",
        "amount_7d",
        "seconds_since_last",
        "amount_vs_card_mean",
        "new_category",
    ]
    assert recompute_check(feats, history, "transaction_time", F.recompute_row, columns) == 200  # type: ignore[arg-type]


def test_a_window_that_counts_the_transaction_itself_is_caught(
    built: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    tx, feats = built
    leaky = feats.with_columns(count_24h=pl.col("count_24h") + 1)  # what closed="both" would produce
    history = PointInTimeFrame.build(
        tx.select("card_key", "transaction_time", "amount", "category"), "card_key", "transaction_time"
    )
    with pytest.raises(LeakageError, match="count_24h"):
        recompute_check(leaky, history, "transaction_time", F.recompute_row, ["count_24h"])  # type: ignore[arg-type]


def test_merchant_fraud_is_invisible_until_its_chargeback_window_closes() -> None:
    t0 = datetime(2026, 1, 1)
    tx = pl.DataFrame(
        {
            "txn_id": [1, 2, 3],
            "merchant_key": ["M1", "M1", "M1"],
            "transaction_time": [t0, t0 + timedelta(days=59), t0 + timedelta(days=61)],
            "is_fraud": [1, 0, 0],
        }
    ).with_columns(pl.col("transaction_time").cast(pl.Datetime("us")))
    rates = F.merchant_fraud_rate(tx, 60).sort("txn_id")
    assert rates["merchant_labelled"].to_list() == [0.0, 0.0, 1.0]
    assert rates["merchant_fraud_rate"][2] > rates["merchant_fraud_rate"][1]


def test_rules_clean_pass_violation_and_refusal() -> None:
    rules = load_rules(ROOT / "rules")
    quiet = pl.DataFrame(
        {
            "txn_id": [1],
            "new_category": [0.0],
            "amount": [900.0],
            "count_10m": [0.0],
            "km_from_last_merchant": [5.0],
            "seconds_since_last": [4000.0],
        }
    )
    assert not rule_columns(quiet, rules).select(pl.col("^rule_.*$")).row(0).__contains__(True)
    loud = pl.DataFrame(
        {
            "txn_id": [1],
            "new_category": [1.0],
            "amount": [rules.new_category_amount + 1],
            "count_10m": [float(rules.burst_count - 1)],
            "km_from_last_merchant": [rules.distant_km + 1],
            "seconds_since_last": [60.0],
        }
    )
    assert rule_columns(loud, rules).select(pl.col("^rule_.*$")).row(0) == (True, True, True)
    with pytest.raises(ValueError, match="no transactions"):
        rule_columns(quiet.clear(), rules)


def test_threshold_chosen_on_validation_is_costed_on_test_and_overlap_is_refused() -> None:
    rng = np.random.default_rng(2)
    y = (rng.random(4000) < 0.02).astype(float)
    p = np.clip(0.02 + 0.6 * y + rng.normal(0, 0.1, 4000), 0, 1)
    a = rng.lognormal(4, 1, 4000)
    ids = np.arange(4000)
    val, test = slice(0, 2000), slice(2000, 4000)
    t, at_t, everything = O.choose_on_validation_report_on_test(
        ids[val], y[val], p[val], a[val], ids[test], y[test], p[test], a[test], 12.0, 35.0
    )
    assert at_t.cost < everything.cost
    assert everything.false_declines == 0 and everything.missed_frauds == int(y[test].sum())
    with pytest.raises(O.DisjointnessError):
        O.choose_on_validation_report_on_test(
            ids[0:2500], y[0:2500], p[0:2500], a[0:2500], ids[test], y[test], p[test], a[test], 12.0, 35.0
        )


def test_labelled_metrics_exclude_the_window_and_a_leak_is_caught() -> None:
    now = datetime(2026, 8, 31, 23, 59)
    times = np.array([np.datetime64(now - timedelta(days=d)) for d in (90, 70, 61, 30, 10, 1)])
    flagged = np.array([True, True, True, True, True, True])
    fraud = np.array([1, 0, 1, 1, 1, 0])
    m = O.labelled_metrics(times, flagged, fraud, now, 60)
    assert (m.labelled, m.unlabelled, m.precision) == (3, 3, pytest.approx(2 / 3))
    O.check_labelled_only(m, times, 60)
    leaky = O.LabelledMetrics(now, 6, 5, 1, 0.8, 1.0)
    with pytest.raises(O.LabelLeakError):
        O.check_labelled_only(leaky, times, 60)
    assert O.naive_precision(
        times, flagged, np.where(times <= np.datetime64(now - timedelta(days=60)), fraud, 0), now
    ) == pytest.approx(2 / 6)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=20, max_size=200), st.floats(0.0, 1.0))
def test_the_queue_point_is_never_below_the_operating_point(scores: list[float], op: float) -> None:
    p = np.array(scores)
    y = (p > 0.5).astype(float)
    if y.sum() == 0:
        y[np.argmax(p)] = 1.0
    assert O.choose_queue_point(y, p, 0.5, op) >= op


def test_the_replay_emits_in_time_order_and_masks_cards() -> None:
    n = 12
    stream = pl.DataFrame(
        {
            "txn_id": list(range(n, 0, -1)),
            "transaction_time": [datetime(2026, 6, 1) + timedelta(minutes=5 * (n - i)) for i in range(n)],
            "card_key": ["Kabcdef0123"] * n,
            "category": ["travel"] * n,
            "amount": [10.0] * n,
            "distance_km": [1.0] * n,
            "merchant_lat": [40.0] * n,
            "merchant_long": [-74.0] * n,
            "score": [0.1] * n,
            "decision": ["approve"] * n,
            "queue": [False] * n,
            "rule_new_category_large": [False] * n,
            "rule_burst": [False] * n,
            "rule_distant_merchant": [False] * n,
            "model_reasons": [""] * n,
            "is_fraud": [0] * n,
        }
    )
    book = LabelBook(stream["transaction_time"].to_numpy(), np.zeros(n, bool), np.zeros(n, int), 60)
    worker = ReplayWorker(stream, 0.0, {"burst": "x"}, book)
    queue = worker.subscribe()
    assert asyncio.run(worker.run()) == n
    events = [queue.get_nowait() for _ in range(n)]
    assert [e["txn_id"] for e in events] == sorted(range(1, n + 1))
    assert all("abcdef" not in e["card"] for e in events) and mask_card("Kabcdef0123") == "Kab*****123"
    with pytest.raises(ValueError, match="empty"):
        ReplayWorker(stream.clear(), 0.0, {}, book)


def test_a_paused_replay_resumes_instead_of_bursting() -> None:
    """A frozen process finds the stream overdue when it thaws; the replay resumes from the pause."""
    import time

    n = 4
    stream = pl.DataFrame(
        {
            "txn_id": list(range(1, n + 1)),
            "transaction_time": [datetime(2026, 6, 1) + timedelta(hours=i) for i in range(n)],
            "card_key": ["Kabcdef0123"] * n,
            "category": ["travel"] * n,
            "amount": [10.0] * n,
            "distance_km": [1.0] * n,
            "merchant_lat": [40.0] * n,
            "merchant_long": [-74.0] * n,
            "score": [0.1, 0.9, 0.1, 0.1],
            "decision": ["approve", "decline", "approve", "approve"],
            "queue": [False, True, False, False],
            "rule_new_category_large": [False] * n,
            "rule_burst": [False] * n,
            "rule_distant_merchant": [False] * n,
            "model_reasons": [""] * n,
            "is_fraud": [0, 1, 0, 0],
        }
    )
    book = LabelBook(stream["transaction_time"].to_numpy(), np.zeros(n, bool), np.zeros(n, int), 60)

    async def freeze(event: dict[str, object]) -> None:
        time.sleep(0.4)  # blocks the loop, as a frozen instance would

    def emitted_at(max_lag: float) -> list[float]:
        worker = ReplayWorker(stream, 0.05, {}, book, on_alert=freeze, max_lag_seconds=max_lag)
        stamps: list[float] = []
        publish = worker._publish

        async def stamped(event: dict[str, object]) -> None:
            stamps.append(asyncio.get_running_loop().time())
            await publish(event)  # type: ignore[arg-type]

        worker._publish = stamped  # type: ignore[method-assign]
        asyncio.run(worker.run())
        return stamps

    # With the pause tolerated forever, the two events after it arrive together.
    bursting = emitted_at(max_lag=1000.0)
    assert bursting[3] - bursting[2] < 0.02
    # With the default treatment, the last one keeps its spacing of one simulated hour.
    resumed = emitted_at(max_lag=0.1)
    assert resumed[3] - resumed[2] >= 0.04


def test_histogram_reproduces_the_anchor_points_exactly() -> None:
    from ledger_desk.operating import cost_at, score_histogram

    rng = np.random.default_rng(3)
    n = 20_000
    y = (rng.random(n) < 0.01).astype(int)
    p = np.clip(rng.beta(0.3, 12, n) + y * rng.random(n) * 0.6, 0, 1)
    amount = rng.gamma(2.0, 40.0, n)
    anchors = [0.0503, 0.2759]
    hist = score_histogram(y, p, amount, anchors)
    assert int(hist["n"].sum()) == n
    assert int(hist["frauds"].sum()) == int(y.sum())
    for t in anchors:
        assert t in hist["lower"].to_list()
        flagged = hist.filter(pl.col("lower") >= t)
        c = cost_at(y, p, amount, t, 12.0, 35.0)
        assert int(flagged["n"].sum()) == c.false_declines + c.caught_frauds
        assert int(flagged["frauds"].sum()) == c.caught_frauds
        missed_amount = float((amount * y).sum()) - float(flagged["fraud_amount"].sum())
        assert abs(c.false_declines * 12.0 + missed_amount + c.missed_frauds * 35.0 - c.cost) < 1e-6


def test_histogram_is_fine_in_the_tail_where_declines_happen() -> None:
    from ledger_desk.operating import score_histogram

    rng = np.random.default_rng(4)
    p = rng.random(50_000) ** 8
    hist = score_histogram(np.zeros(p.size, dtype=int), p, np.ones(p.size), [])
    top = hist.filter(pl.col("lower") >= float(np.quantile(p, 0.99)))
    # A percent of the scores is split across many bins, so the slider moves in small steps there.
    assert top.height >= 100
    assert int(top["n"].max()) <= 0.001 * p.size


def test_histogram_refuses_no_scores() -> None:
    from ledger_desk.operating import score_histogram

    with pytest.raises(ValueError):
        score_histogram(np.array([]), np.array([]), np.array([]), [0.5])
