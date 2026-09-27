"""fraud_card: train, choose the operating point on validation, report on test, and write the scored stream.

Temporal split by transaction month:

    train       2025-09 to 2026-03   labels observable by the end of May
    validation  2026-04 to 2026-05   chooses the operating point and the queue point
    test        2026-06 to 2026-08   reported, and replayed on the desk

As of the end of August, a large part of the test stream is still inside the
chargeback window. The test metrics in the validation report use the labels as
they eventually arrive (Sparkov knows them); the desk's live metrics never do.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import polars as pl
from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest
from ledger_core.pit import PointInTimeFrame, recompute_check
from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import discrimination, reliability, subgroup_table
from ledger_models.gates import Gate, run_gates
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory
from ledger_scorecard.policy_files import load_proxies
from ledger_scorecard.scorecard import check_proxies
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ledger_desk import features as F
from ledger_desk import operating as O
from ledger_desk.rules import load_rules, rule_columns

FEATURE_WORDS = {
    "amount": "large amount",
    "log_amount": "large amount",
    "amount_vs_card_mean": "amount far above this card's usual",
    "new_category": "first purchase in this category",
    "count_10m": "several purchases in the last ten minutes",
    "count_1h": "several purchases in the last hour",
    "count_24h": "unusual number of purchases today",
    "count_7d": "unusual number of purchases this week",
    "amount_1h": "high spend in the last hour",
    "amount_24h": "high spend today",
    "amount_7d": "high spend this week",
    "seconds_since_last": "unusual gap since the last purchase",
    "hour": "time of day",
    "weekday": "day of the week",
    "distance_km": "distance from the cardholder's home",
    "merchant_fraud_rate": "merchant's confirmed fraud history",
    "merchant_labelled": "merchant with little history",
    "km_from_last_merchant": "far from the previous merchant",
    "category": "merchant category",
}
NEGATIVE_SHARE = 0.25


def split_of(month: pl.Expr) -> pl.Expr:
    return (
        pl.when(month <= "2026-03")
        .then(pl.lit("train"))
        .when(month <= "2026-05")
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
    )


def _matrix(frame: pl.DataFrame, levels: list[str]) -> np.ndarray:
    cols = [frame[c].cast(pl.Float64).to_numpy() for c in F.NUMERIC_FEATURES]
    mapping = {v: float(i) for i, v in enumerate(levels)}
    cols.append(np.array([mapping.get(v, np.nan) for v in frame["category"].to_list()]))
    return np.column_stack(cols)


def _age_band(birth_year: pl.Expr, year: int) -> pl.Expr:
    age = year - birth_year
    return (
        pl.when(age < 25)
        .then(pl.lit("under 25"))
        .when(age < 40)
        .then(pl.lit("25 to 39"))
        .when(age < 60)
        .then(pl.lit("40 to 59"))
        .otherwise(pl.lit("60 and over"))
    )


def leakage_check(feats: pl.DataFrame, tx: pl.DataFrame, seed: int) -> int:
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

    def recompute(past: pl.DataFrame, row: dict[str, object]) -> dict[str, float | None]:
        return F.recompute_row(past, row)

    # Transactions sharing a card and a timestamp are excluded from the sample: "before"
    # is ambiguous between them, and the features treat them as simultaneous.
    ties = feats.group_by("card_key", "transaction_time").len().filter(pl.col("len") > 1)
    sample = feats.join(
        ties.select("card_key", "transaction_time"), on=["card_key", "transaction_time"], how="anti"
    )
    return recompute_check(sample, history, "transaction_time", recompute, columns, seed=seed)  # type: ignore[arg-type]


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> ModelResult:
    fd = cfg.fraud_desk
    cb = cfg.censoring.chargeback_window_days
    out = models_dir / "fraud_card"
    out.mkdir(parents=True, exist_ok=True)
    tx = pl.read_parquet(root / "data" / "staged" / "sparkov" / "card_transactions.parquet")
    feats = (
        F.build(tx, cb)
        .with_columns(
            month=pl.col("transaction_time").dt.strftime("%Y-%m"),
        )
        .with_columns(split=split_of(pl.col("month")), age_band=_age_band(pl.col("birth_year"), 2026))
    )
    proxies = load_proxies(root / "rules")
    check_proxies(F.FEATURES, proxies)
    rules = load_rules(root / "rules")
    fired = rule_columns(feats, rules)
    feats = feats.join(fired, on="txn_id", how="left")
    levels = sorted(feats["category"].unique().to_list())

    train = feats.filter(pl.col("split") == "train")
    val = feats.filter(pl.col("split") == "validation")
    test = feats.filter(pl.col("split") == "test")
    params = {
        "objective": "binary",
        "learning_rate": 0.08,
        "num_leaves": 31,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "seed": cfg.seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 2,
        "verbose": -1,
    }
    # Every fraud and one genuine transaction in four, the genuine ones weighted by four, so
    # the fit sees the same fraud rate it will score at while training four times faster.
    rng = np.random.default_rng(cfg.seed)
    keep = (train["is_fraud"].to_numpy() == 1) | (rng.random(train.height) < NEGATIVE_SHARE)
    fit_rows = train.filter(pl.Series(keep))
    weights = np.where(fit_rows["is_fraud"].to_numpy() == 1, 1.0, 1.0 / NEGATIVE_SHARE)
    dtrain = lgb.Dataset(
        _matrix(fit_rows, levels),
        fit_rows["is_fraud"].to_numpy(),
        weight=weights,
        feature_name=F.FEATURES,
        categorical_feature=[len(F.NUMERIC_FEATURES)],
        free_raw_data=False,
    )
    dval = lgb.Dataset(_matrix(val, levels), val["is_fraud"].to_numpy(), reference=dtrain)
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=500,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    booster.save_model(str(out / "model.txt"))
    (out / "category_levels.json").write_text(json.dumps(levels) + "\n")

    def score(frame: pl.DataFrame) -> np.ndarray:
        return np.asarray(booster.predict(_matrix(frame, levels)))

    p_train, p_val, p_test = score(train), score(val), score(test)
    y_train, y_val, y_test = (f["is_fraud"].to_numpy().astype(float) for f in (train, val, test))
    a_val, a_test = val["amount"].to_numpy(), test["amount"].to_numpy()

    # Baselines on the same test months.
    scaler = StandardScaler()
    num = [c for c in F.NUMERIC_FEATURES]

    def design(frame: pl.DataFrame) -> np.ndarray:
        x = frame.select([pl.col(c).cast(pl.Float64).fill_null(0.0) for c in num]).to_numpy()
        cats = np.column_stack([(frame["category"] == lv).cast(pl.Float64).to_numpy() for lv in levels[1:]])
        return np.column_stack([x, cats])

    logit = LogisticRegression(max_iter=3000, C=1.0)
    logit.fit(scaler.fit_transform(design(train)), y_train)
    p_logit = logit.predict_proba(scaler.transform(design(test)))[:, 1]
    base = discrimination(y_test, np.full(y_test.size, float(y_train.mean())))

    # The operating point and the queue point come from validation only.
    t_op, at_op, approve_all = O.choose_on_validation_report_on_test(
        val["txn_id"].to_numpy(),
        y_val,
        p_val,
        a_val,
        test["txn_id"].to_numpy(),
        y_test,
        p_test,
        a_test,
        fd.cost_false_decline,
        fd.cost_missed_fraud_handling,
    )
    t_queue = O.choose_queue_point(y_val, p_val, fd.queue_precision_floor, t_op)
    t_acc = O.accuracy_threshold(y_val, p_val)
    at_acc = O.cost_at(y_test, p_test, a_test, t_acc, fd.cost_false_decline, fd.cost_missed_fraud_handling)
    from ledger_models.evaluate import confusion_at

    c_op = confusion_at(y_test, p_test, t_op)
    c_queue = confusion_at(y_test, p_test, t_queue)
    curve_val = O.cost_curve(
        y_val, p_val, a_val, fd.cost_false_decline, fd.cost_missed_fraud_handling
    ).with_columns(sample=pl.lit("validation"))
    curve_test = O.cost_curve(
        y_test,
        p_test,
        a_test,
        fd.cost_false_decline,
        fd.cost_missed_fraud_handling,
        thresholds=curve_val["threshold"].to_numpy(),
    ).with_columns(sample=pl.lit("test"))
    pl.concat([curve_val, curve_test]).write_parquet(out / "cost_curve.parquet")

    # Precision and recall across thresholds on test, for the PR curve.
    pr_rows = []
    for t in np.unique(np.quantile(p_test, np.linspace(0.80, 0.9995, 160))):
        c = confusion_at(y_test, p_test, float(t))
        pr_rows.append(
            {
                "threshold": float(t),
                "precision": c["precision"],
                "recall": c["recall"],
                "flagged": c["flagged"],
            }
        )
    pl.DataFrame(pr_rows).write_parquet(out / "pr_curve.parquet")

    # Decisions on the scored history (validation and test), rules in plain words, model reasons.
    history = pl.concat(
        [val.with_columns(score=pl.Series(p_val)), test.with_columns(score=pl.Series(p_test))]
    )
    rule_any = (
        history["rule_new_category_large"] | history["rule_burst"] | history["rule_distant_merchant"]
    ).to_numpy()
    decision = O.decide(history["score"].to_numpy(), rule_any, t_op)
    history = history.with_columns(
        decision=pl.Series(decision),
        queue=pl.col("score") >= t_queue,
        label_observable_at=pl.col("transaction_time") + pl.duration(days=cb),
    )
    # Feature contributions only where the desk has to explain itself: reviews and declines.
    names = np.array(F.FEATURES)
    reasons = [""] * history.height
    explain = np.flatnonzero(decision != "approve")
    if explain.size:
        contrib = np.asarray(booster.predict(_matrix(history[explain.tolist()], levels), pred_contrib=True))[
            :, :-1
        ]
        top = np.argsort(-contrib, axis=1)[:, :2]
        for k, i in enumerate(explain):
            reasons[i] = "; ".join(FEATURE_WORDS[names[j]] for j in top[k] if contrib[k, j] > 0)
    history = history.with_columns(model_reasons=pl.Series(reasons))
    columns = [
        "txn_id",
        "card_key",
        "transaction_time",
        "month",
        "split",
        "category",
        "amount",
        "distance_km",
        "merchant_lat",
        "merchant_long",
        "customer_lat",
        "customer_long",
        "gender",
        "age_band",
        "score",
        "decision",
        "queue",
        "rule_new_category_large",
        "rule_burst",
        "rule_distant_merchant",
        "model_reasons",
        "is_fraud",
        "label_observable_at",
    ]
    history.select(columns).write_parquet(out / "scored_stream.parquet", compression="zstd")
    # What the API needs to serve the model and replay the desk.
    (out / "serving.json").write_text(
        json.dumps(
            {
                "features": F.FEATURES,
                "category_levels": levels,
                "operating_point": t_op,
                "queue_point": t_queue,
            },
            indent=1,
        )
        + "\n"
    )
    replay_cols = [
        "txn_id",
        "transaction_time",
        "card_key",
        "category",
        "amount",
        "distance_km",
        "merchant_lat",
        "merchant_long",
        "score",
        "decision",
        "queue",
        "rule_new_category_large",
        "rule_burst",
        "rule_distant_merchant",
        "model_reasons",
        "is_fraud",
    ]
    history.filter(pl.col("split") == "test").select(replay_cols).write_parquet(
        out / "replay_stream.parquet", compression="zstd"
    )
    history.filter(pl.col("split") == "validation").select(
        "transaction_time", declined=pl.col("decision") == "decline", is_fraud=pl.col("is_fraud")
    ).write_parquet(out / "replay_history.parquet", compression="zstd")

    # Late labels: what the desk could know on each day of the test months.
    times = history["transaction_time"].to_numpy()
    flagged = (history["decision"] == "decline").to_numpy()
    is_fraud = history["is_fraud"].to_numpy()
    lag_rows = []
    day = datetime(2026, 6, 1)
    while day <= datetime(2026, 8, 31):
        as_of = day + timedelta(hours=23, minutes=59, seconds=59)
        lm = O.labelled_metrics(times, flagged, is_fraud, as_of, cb)
        lag_rows.append(
            {
                "day": day.date(),
                "decisions": lm.decisions,
                "labelled": lm.labelled,
                "unlabelled": lm.unlabelled,
                "precision_labelled": lm.precision,
                "recall_labelled": lm.recall,
            }
        )
        day += timedelta(days=1)
    lag = pl.DataFrame(lag_rows)
    lag.write_parquet(out / "label_lag_daily.parquet")
    end = datetime(2026, 8, 31, 23, 59, 59)
    final = O.labelled_metrics(times, flagged, is_fraud, end, cb)
    O.check_labelled_only(final, times, cb)
    test_mask = (history["split"] == "test").to_numpy()
    test_unlabelled = int((test_mask & (times > np.datetime64(end - timedelta(days=cb)))).sum())
    truth_known = np.where(times <= np.datetime64(end - timedelta(days=cb)), is_fraud, 0)
    naive = O.naive_precision(times[test_mask], flagged[test_mask], truth_known[test_mask], end)

    # Rules on the test months.
    rule_rows = []
    for key, statement in rules.statements.items():
        hit = test[f"rule_{key}"].to_numpy()
        rule_rows.append(
            {
                "rule": statement,
                "fired": int(hit.sum()),
                "precision": float(y_test[hit].mean()) if hit.sum() else None,
                "recall": float(y_test[hit].sum() / y_test.sum()),
            }
        )
    rules_table = pl.DataFrame(rule_rows)

    # Fairness at the operating point: false positive rate and recall by the demographics Sparkov generates.
    fair_gender = subgroup_table(y_test, p_test, test["gender"].to_numpy(), threshold=t_op)
    fair_age = subgroup_table(y_test, p_test, test["age_band"].to_numpy(), threshold=t_op)
    fprs = [x for x in fair_age["fpr"].to_list() + fair_gender["fpr"].to_list() if x is not None]
    fpr_ratio = min(fprs) / max(fprs) if fprs and max(fprs) > 0 else None
    age_fprs = [x for x in fair_age["fpr"].to_list() if x is not None]
    age_ratio = min(age_fprs) / max(age_fprs) if age_fprs and max(age_fprs) > 0 else None

    leak_rows = leakage_check(test, tx, cfg.seed)

    samples = {
        "development": discrimination(y_train, p_train),
        "validation": discrimination(y_val, p_val),
        "test": discrimination(y_test, p_test),
    }
    tier, tier_reason = tier_for(decides_automatically=True, informs_person=True, complex_method=True)
    gates = [
        Gate("auroc", "Test AUROC at or above the floor", "at_least", 0.90),
        Gate("vs_logistic", "Test average precision above the logistic benchmark", "at_least", 0.0),
        Gate(
            "saving",
            "Test cost at the operating point below approving everything (share saved)",
            "at_least",
            0.30,
        ),
        Gate(
            "fpr_ratio",
            "Lowest over highest false positive rate across age bands at the operating point",
            "at_least",
            0.50,
            critical=False,
        ),
        Gate("leakage", "Point in time recompute of sampled rows", "at_least", 200),
        Gate("ece", "Expected calibration error on test", "at_most", 0.01, critical=False),
    ]
    logit_d = discrimination(y_test, p_logit)
    measured = {
        "auroc": samples["test"].auroc,
        "vs_logistic": samples["test"].average_precision - logit_d.average_precision,
        "saving": 1 - at_op.cost / approve_all.cost,
        "fpr_ratio": age_ratio,
        "leakage": float(leak_rows),
        "ece": samples["test"].ece,
    }
    card = ModelCard(
        model_id="fraud_card",
        function="f04",
        title="Card transaction fraud (the desk's model)",
        purpose="Score every card authorisation at the moment it happens and decide approve, review or decline at a cost based operating point",
        tier=tier,
        tier_reason=tier_reason,
        role="sole",
        status="in use",
        prediction_time="The instant of the authorisation; features use only the card's and the merchant's history strictly before it",
        outcome=f"Fraud as confirmed after the {cb} day chargeback window",
        population="Sparkov card transactions, September 2025 to August 2026",
        backend="replayed",
        method="LightGBM on point in time velocity, recency, novelty and merchant history features, early stopped on validation",
        features=list(F.FEATURES),
        lines={
            "trained": "On September 2025 to March 2026, whose labels had all arrived by the end of May.",
            "timed": "Every feature is computed from strictly earlier transactions; a leakage test recomputes 200 sampled rows from raw history.",
            "calibrated": "Reliability on the test months is published; the cost curve uses scores as ranks, not as probabilities.",
            "useful": "Beats the base rate and a logistic model on the same features, and saves most of the cost of approving everything.",
            "fair": "False positive rate and recall by cardholder gender and age band at the operating point.",
            "gated": "Every gate in its validation report, including the cost saving measured on data the threshold never saw.",
            "served": "POST /v1/score/fraud_card and the desk's replay worker in the API; recorded replay on the site.",
            "integrated": "Decides approve, review or decline on the desk; alerts at the queue point go to the analyst queue first.",
            "monitored": "Precision and recall over labelled transactions only, with the unlabelled count beside them; weekly score PSI.",
            "documented": "This validation report, docs/fraud-desk.md and the rule file.",
            "bounded": "Scores card authorisations only; the rules can send a transaction to review but never decline it alone.",
            "validated": "This report, rendered from the manifest before the desk uses the model.",
            "explainable": "Every review or decline shows the rules that fired and the two features that moved the score most, in plain words.",
        },
    )
    result = ModelResult(
        card=card,
        samples=samples,
        baselines={"Base rate": base, "Logistic on the same features": logit_d},
        gates=run_gates(gates, measured),
        reliability=reliability(y_test, p_test),
        subgroups=pl.concat(
            [
                fair_gender.with_columns(pl.lit("gender").alias("_d")),
                fair_age.with_columns(pl.lit("age").alias("_d")),
            ]
        ).drop("_d"),
        monitoring=[
            (
                "Precision over labelled decisions, weekly",
                f"below {fd.queue_precision_floor:.0%} at the queue point for two weeks",
                "Review the threshold on the latest labelled month",
            ),
            (
                "Unlabelled decisions inside the chargeback window",
                "reported beside every precision figure",
                "None: it is context, not a trigger",
            ),
            ("Score PSI, weekly against validation", f"above {cfg.model_risk.psi_breach:g}", "Revalidate"),
            (
                "Rule precision on labelled months",
                "any rule below twice the base rate",
                "Retire or retune the rule",
            ),
        ],
        last_validated=cfg.calendar.as_of.isoformat(),
        extra_values={
            "train_period": ("September 2025 to March 2026", "text"),
            "validation_period": ("April and May 2026", "text"),
            "test_period": ("June to August 2026", "text"),
            "operating_point": (t_op, "float4"),
            "queue_point": (t_queue, "float4"),
            "accuracy_point": (t_acc, "float4"),
            "cost_op": (at_op.cost, "usd0"),
            "cost_all": (approve_all.cost, "usd0"),
            "cost_acc": (at_acc.cost, "usd0"),
            "saving": (approve_all.cost - at_op.cost, "usd0"),
            "saving_share": (1 - at_op.cost / approve_all.cost, "pct1"),
            "precision_op": (c_op["precision"], "pct1"),
            "recall_op": (c_op["recall"], "pct1"),
            "flagged_op": (c_op["flagged"], "int"),
            "fpr_op": (c_op["fpr"], "pct3"),
            "precision_queue": (c_queue["precision"], "pct1"),
            "recall_queue": (c_queue["recall"], "pct1"),
            "flagged_queue": (c_queue["flagged"], "int"),
            "accuracy_flagged": (at_acc.false_declines + at_acc.caught_frauds, "int"),
            "test_transactions": (test.height, "int"),
            "test_frauds": (int(y_test.sum()), "int"),
            "unlabelled_test": (test_unlabelled, "int"),
            "unlabelled_share": (test_unlabelled / test.height, "pct1"),
            "labelled_precision_as_of": (final.precision, "pct1"),
            "labelled_recall_as_of": (final.recall, "pct1"),
            "naive_precision_as_of": (naive, "pct1"),
            "leakage_rows": (leak_rows, "int"),
            "trees": (booster.num_trees(), "int"),
            "fpr_ratio_age": (age_ratio, "float2"),
            "fpr_ratio_all": (fpr_ratio, "float2"),
            "cost_false_decline": (fd.cost_false_decline, "usd2"),
            "cost_handling": (fd.cost_missed_fraud_handling, "usd2"),
        },
        extra_tables={
            "rules": rules_table,
            "operating_points": pl.DataFrame(
                {
                    "point": [
                        "Cost minimum (operating point)",
                        "Queue point",
                        "Accuracy maximum",
                        "Approve everything",
                    ],
                    "threshold": [t_op, t_queue, t_acc, None],
                    "declined_or_queued": [
                        c_op["flagged"],
                        c_queue["flagged"],
                        float(at_acc.false_declines + at_acc.caught_frauds),
                        0.0,
                    ],
                    "cost": [at_op.cost, None, at_acc.cost, approve_all.cost],
                }
            ),
        },
        extra_formats={
            "rules": ["text", "int", "pct1", "pct1"],
            "operating_points": ["text", "float4", "int", "usd0"],
        },
    )
    challenges = read_challenges(root / "DECISIONS.md")
    m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
    put_result(m, result, challenges)
    m.save(out / "manifest.json")
    write_inventory(models_dir, [inventory_row(result)])
    return result
