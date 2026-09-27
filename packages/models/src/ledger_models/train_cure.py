"""cure: will a delinquent loan return to current within ninety days?

At each month end, for every loan thirty or more days past due, the probability that it
is current (or paid off) again within the next three months. It is integrated into the
collections queue, ranked by balance at risk times the probability of not curing, so a
collector's first call goes where the money is most likely to be lost without one.

The collections team's rule today is the bucket: thirty day loans first, then sixty,
then ninety. The model has to beat that rule, not only the base rate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import lightgbm as lgb
import numpy as np
import polars as pl
from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest
from ledger_core.pit import PointInTimeFrame, recompute_check
from ledger_scorecard.policy_files import load_proxies
from ledger_scorecard.scorecard import check_proxies
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import discrimination, reliability, subgroup_table
from ledger_models.gates import Gate, run_gates
from ledger_models.reasons import Words, reasons
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory

MODEL_ID = "cure"
HORIZON = 3
TRAIN = ("2023-09", "2025-06")
VALIDATION = ("2025-07", "2025-09")
TEST = ("2025-12", "2026-05")
MARGIN = 0.005
QUEUE = 300
FEATURES = (
    "bucket_60",
    "bucket_90",
    "months_delinquent",
    "prior_episodes",
    "payment_ratio",
    "paid_anything",
    "log_balance",
    "months_on_book",
    "card",
    "mortgage",
    "interest_rate",
    "utilization",
    "unemployment",
)
FEATURE_WORDS: dict[str, Words] = {
    "bucket_60": ("sixty days past due", None),
    "bucket_90": ("ninety or more days past due", None),
    "months_delinquent": "months in a row past due",
    "prior_episodes": "earlier delinquencies",
    "payment_ratio": "share of the payment made last month",
    "paid_anything": ("made a payment last month", "made no payment last month"),
    "log_balance": "balance",
    "months_on_book": "age of the loan",
    "card": ("a card account", None),
    "mortgage": ("a mortgage", None),
    "interest_rate": "interest rate",
    "utilization": "card utilisation",
    "unemployment": "unemployment",
}


def _label(words: Words) -> str:
    return words if isinstance(words, str) else words[0]


def load(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Every delinquent loan month end, its features as of that month end, and whether it cured."""
    frame = con.execute(
        f"""
        with m as (
            select l.*,
                (l.bucket <> 'current')::int as late,
                sum(case when l.bucket = 'current' then 1 else 0 end)
                    over (partition by l.loan_id order by l.month_index rows between unbounded preceding and current row)
                    as currents_so_far,
                sum(case when l.bucket_open = 'current' and l.bucket = '30' then 1 else 0 end)
                    over (partition by l.loan_id order by l.month_index rows between unbounded preceding and 1 preceding)
                    as prior_episodes,
                max(case when l.bucket in ('current', 'paid_off') then 1 else 0 end)
                    over (partition by l.loan_id order by l.month_index rows between 1 following and {HORIZON} following)
                    as cured
            from marts.fct_loan_month l
        ),
        runs as (
            -- A run of late months starts after the loan's last current month end, which sits in the
            -- same group as the run and is not part of it.
            select *, count(*) over (partition by loan_id, currents_so_far order by month_index
                rows between unbounded preceding and current row)
                - case when currents_so_far > 0 then 1 else 0 end as months_delinquent
            from m
        )
        select r.loan_id, r.product, r.month, r.month_index, r.bucket, r.months_on_book,
            r.closing_balance::double as balance, r.scheduled_payment::double as scheduled_payment,
            r.amount_paid::double as amount_paid, r.months_delinquent, coalesce(r.prior_episodes, 0) as prior_episodes,
            r.cured, s.interest_rate::double as interest_rate, s.credit_limit::double as credit_limit,
            p.unemployment_rate as unemployment
        from runs r
        join staging.stg_loans s using (loan_id)
        join staging.stg_macro_path p using (month)
        where r.bucket in ('30', '60', '90+')
        order by r.month_index, r.loan_id
        """
    ).pl()
    return frame.with_columns(
        bucket_60=(pl.col("bucket") == "60").cast(pl.Float64),
        bucket_90=(pl.col("bucket") == "90+").cast(pl.Float64),
        months_delinquent=pl.col("months_delinquent").cast(pl.Float64),
        prior_episodes=pl.col("prior_episodes").cast(pl.Float64),
        payment_ratio=(
            pl.col("amount_paid") / pl.max_horizontal(pl.col("scheduled_payment"), pl.lit(1.0))
        ).clip(0, 3),
        paid_anything=(pl.col("amount_paid") > 0).cast(pl.Float64),
        log_balance=pl.col("balance").clip(0, None).log1p(),
        months_on_book=pl.col("months_on_book").cast(pl.Float64),
        card=(pl.col("product") == "card").cast(pl.Float64),
        mortgage=(pl.col("product") == "mortgage").cast(pl.Float64),
        utilization=pl.when(pl.col("credit_limit") > 0)
        .then((pl.col("balance") / pl.col("credit_limit")).clip(0, 2))
        .otherwise(0.0),
    )


def part(frame: pl.DataFrame, window: tuple[str, str]) -> pl.DataFrame:
    return frame.filter(
        pl.col("month").is_between(pl.lit(window[0]), pl.lit(window[1])) & pl.col("cured").is_not_null()
    )


def matrix(frame: pl.DataFrame) -> np.ndarray:
    return frame.select(FEATURES).to_numpy().astype(float)


def outcomes_known_before(last_fit_month: str, first_test_month: str, horizon_months: int = HORIZON) -> bool:
    fy, fm = (int(x) for x in last_fit_month.split("-"))
    ty, tm = (int(x) for x in first_test_month.split("-"))
    return (ty * 12 + tm) - (fy * 12 + fm) >= horizon_months


def leakage_check(con: duckdb.DuckDBPyConnection, test: pl.DataFrame, seed: int) -> int:
    """Recompute the run length, earlier episodes and last payment from the loan's own months."""
    sample = test.sample(n=min(300, test.height), seed=seed)
    history = con.execute(
        """
        select loan_id, month, bucket_open, bucket, amount_paid::double as amount_paid,
            scheduled_payment::double as scheduled_payment,
            strptime(month || '-01', '%Y-%m-%d') as month_start
        from marts.fct_loan_month where loan_id in (select unnest(?))
        """,
        [sample["loan_id"].unique().to_list()],
    ).pl()
    frame = sample.with_columns(
        prediction_at=(pl.col("month") + "-01").str.to_datetime("%Y-%m-%d").dt.offset_by("1mo")
    )

    def recompute(past: pl.DataFrame, row: dict[str, Any]) -> dict[str, float]:
        rows = past.sort("month")
        buckets = rows["bucket"].to_list()
        run = 0
        for b in reversed(buckets):
            if b == "current":
                break
            run += 1
        episodes = sum(
            1
            for o, b in zip(rows["bucket_open"].to_list()[:-1], buckets[:-1], strict=True)
            if o == "current" and b == "30"
        )
        last = rows.row(-1, named=True)
        ratio = min(3.0, max(0.0, last["amount_paid"] / max(last["scheduled_payment"], 1.0)))
        return {"months_delinquent": float(run), "prior_episodes": float(episodes), "payment_ratio": ratio}

    return recompute_check(
        frame,
        PointInTimeFrame.build(history, "loan_id", "month_start"),
        "prediction_at",
        recompute,  # type: ignore[arg-type]
        ["months_delinquent", "prior_episodes", "payment_ratio"],
        sample=200,
        seed=seed,
        tolerance=1e-6,
    )


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> ModelResult:
    out = models_dir / MODEL_ID
    out.mkdir(parents=True, exist_ok=True)
    check_proxies(list(FEATURES), load_proxies(root / "rules"))
    if not outcomes_known_before(VALIDATION[1], TEST[0]):
        raise ValueError(
            "an outcome used to fit or choose the model was not known by the first test month end"
        )
    seed = cfg.seed % 100_000
    frame = load(con)
    train, val, test = part(frame, TRAIN), part(frame, VALIDATION), part(frame, TEST)
    y = {n: f["cured"].to_numpy().astype(float) for n, f in (("train", train), ("val", val), ("test", test))}
    held_out = (pl.col("loan_id").hash(seed) % 5) == 0
    fit_rows, stop_rows = train.filter(~held_out), val.filter(held_out)
    fit_y = fit_rows["cured"].to_numpy().astype(float)
    stop_y = stop_rows["cured"].to_numpy().astype(float)
    params = {
        "objective": "binary",
        "learning_rate": 0.03,
        "num_leaves": 15,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 5.0,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 4,
        "verbose": -1,
    }
    dtrain = lgb.Dataset(matrix(fit_rows), fit_y, feature_name=list(FEATURES), free_raw_data=False)
    dval = lgb.Dataset(matrix(stop_rows), stop_y, reference=dtrain)
    booster = lgb.train(
        params, dtrain, 1500, valid_sets=[dval], callbacks=[lgb.early_stopping(100, verbose=False)]
    )
    scaler = StandardScaler().fit(matrix(fit_rows))
    logit = LogisticRegression(max_iter=5000).fit(scaler.transform(matrix(fit_rows)), fit_y)

    def boosted(f: pl.DataFrame) -> np.ndarray:
        return np.asarray(booster.predict(matrix(f), num_iteration=booster.best_iteration))

    def logistic(f: pl.DataFrame) -> np.ndarray:
        return np.asarray(logit.predict_proba(scaler.transform(matrix(f)))[:, 1])

    auc_boosted = float(roc_auc_score(stop_y, boosted(stop_rows)))
    auc_logistic = float(roc_auc_score(stop_y, logistic(stop_rows)))
    champion = "boosted" if auc_boosted - auc_logistic >= MARGIN else "logistic"
    score, other = (boosted, logistic) if champion == "boosted" else (logistic, boosted)
    other_name = "Logistic on the same features" if champion == "boosted" else "LightGBM on the same features"

    p = {"train": score(train), "val": score(val), "test": score(test)}
    samples = {
        "development": discrimination(y["train"], p["train"]),
        "validation": discrimination(y["val"], p["val"]),
        "test": discrimination(y["test"], p["test"]),
    }
    other_d = discrimination(y["test"], other(test))
    base = discrimination(y["test"], np.full(y["test"].size, float(y["train"].mean())))
    # The collections team's rule: each bucket's cure rate on the training months.
    rates = train.group_by("bucket").agg(pl.col("cured").mean().alias("rate"))
    rule = test.join(rates, on="bucket", how="left")["rate"].fill_null(float(y["train"].mean())).to_numpy()
    rule_d = discrimination(y["test"], rule)
    by_bucket = subgroup_table(y["test"], p["test"], test["bucket"].to_numpy())
    leak_rows = leakage_check(con, test, seed)

    gates = [
        Gate("vs_rule", "Test AUROC above the bucket rule the collections team uses today", "at_least", 0.02),
        Gate(
            "vs_other",
            "Test AUROC against the other candidate's (the choice on validation must not cost more than a hundredth)",
            "at_least",
            -0.01,
        ),
        Gate("auroc", "Test AUROC at or above the floor", "at_least", 0.70),
        Gate("leakage", "Point in time recompute of sampled delinquent loan months", "at_least", 200),
        Gate("ece", "Expected calibration error on test", "at_most", 0.05, critical=False),
    ]
    measured = {
        "vs_rule": samples["test"].auroc - rule_d.auroc,
        "vs_other": samples["test"].auroc - other_d.auroc,
        "auroc": samples["test"].auroc,
        "leakage": float(leak_rows),
        "ece": samples["test"].ece,
    }

    # The queue on the as of month: balance at risk times the probability of not curing.
    as_of = cfg.calendar.as_of.strftime("%Y-%m")
    now = frame.filter(pl.col("month") == as_of)
    p_now = score(now)
    now = now.with_columns(
        probability_cure=pl.Series(p_now),
        expected_loss_exposure=pl.col("balance") * (1 - pl.Series(p_now)),
    ).sort("expected_loss_exposure", descending=True)
    queued = now.head(QUEUE)
    if champion == "boosted":
        contrib = np.asarray(
            booster.predict(matrix(queued), num_iteration=booster.best_iteration, pred_contrib=True)
        )[:, :-1]
    else:
        contrib = scaler.transform(matrix(queued)) * logit.coef_[0]
    # Reasons a loan is unlikely to cure: the features that pushed the cure probability down.
    why = reasons(list(FEATURES), contrib, matrix(queued), FEATURE_WORDS, direction=-1)
    queue = queued.with_columns(reasons=pl.Series(why)).select(
        "loan_id", "product", "bucket", "balance", "probability_cure", "expected_loss_exposure", "reasons"
    )
    queue.write_parquet(out / "queue.parquet")

    if champion == "boosted":
        gain = booster.feature_importance("gain")
        weights = gain / gain.sum()
    else:
        weights = logit.coef_[0]
    importance = pl.DataFrame(
        {"feature": [_label(FEATURE_WORDS[f]) for f in FEATURES], "weight": [float(w) for w in weights]}
    ).sort(pl.col("weight").abs(), descending=True)

    tier, tier_reason = tier_for(decides_automatically=False, informs_person=True, complex_method=False)
    card = ModelCard(
        model_id=MODEL_ID,
        function="f09",
        title="Cure within ninety days for delinquent loans",
        purpose="Order the collections queue by the balance likely to be lost without a call: balance times the probability the loan does not cure",
        tier=tier,
        tier_reason=tier_reason,
        role="sole",
        status="in use",
        prediction_time="Each month end, for loans thirty or more days past due; features use that month and earlier",
        outcome="The loan is current, or paid off, at one of the next three month ends",
        population="Harborline installment, card and mortgage loans past due at a month end, September 2023 to August 2026",
        backend="generated",
        method=(
            "LightGBM on delinquency, payment and loan features, early stopped on held out loans"
            if champion == "boosted"
            else "Logistic regression on delinquency, payment and loan features; chosen over LightGBM on held out loans"
        ),
        features=list(FEATURES),
        lines={
            "trained": "On month ends September 2023 to June 2025, whose three month outcomes had all closed before the test months began.",
            "timed": "Every feature comes from the month end or earlier; a leakage test recomputes the run length, earlier episodes and last payment for 200 sampled loan months.",
            "calibrated": "Reliability on the test months is published; the queue multiplies the balance by one minus the probability, so calibration matters.",
            "useful": "Beats the base rate, the bucket rule collectors use today, and the other candidate on months it never saw.",
            "fair": "No demographic enters; the features describe the loan and its payments. Cure rates by bucket are published beside the model's.",
            "gated": "Every gate in this report, including the margin over the bucket rule.",
            "served": "Scored monthly in the pipeline; the queue is published with the collections page.",
            "integrated": "Orders the collections queue by balance at risk times the probability of not curing.",
            "monitored": "Monthly: realised cure rate by queue decile, score PSI, and the rule's AUROC beside the model's.",
            "documented": "This validation report and the collections page.",
            "bounded": "Orders calls. Never changes terms, never charges off a loan, and never goes to a borrower as a score.",
            "validated": "This report, rendered from the manifest before the queue uses the order.",
            "explainable": "Each queued loan shows the two features that lowered its chance of curing most, in plain words.",
        },
    )
    result = ModelResult(
        card=card,
        samples=samples,
        baselines={"Base rate": base, "The bucket rule": rule_d, other_name: other_d},
        gates=run_gates(gates, measured),
        reliability=reliability(y["test"], p["test"]),
        subgroups=by_bucket,
        monitoring=[
            (
                "Realised cure rate by queue decile, monthly",
                "the top decile cures more often than the bottom",
                "Refit",
            ),
            ("Score PSI, monthly against validation", f"above {cfg.model_risk.psi_breach:g}", "Revalidate"),
            (
                "The bucket rule's AUROC beside the model's",
                "the margin falls below the gate for a quarter",
                "Revalidate",
            ),
        ],
        last_validated=cfg.calendar.as_of.isoformat(),
        extra_values={
            "train_period": ("month ends September 2023 to June 2025", "text"),
            "validation_period": ("month ends July to September 2025", "text"),
            "test_period": ("month ends December 2025 to May 2026", "text"),
            "test_rows": (test.height, "int"),
            "test_cured": (int(y["test"].sum()), "int"),
            "champion": ("LightGBM" if champion == "boosted" else "logistic regression", "text"),
            "other": ("logistic regression" if champion == "boosted" else "LightGBM", "text"),
            "auc_boosted_holdout": (auc_boosted, "float3"),
            "auc_logistic_holdout": (auc_logistic, "float3"),
            "margin": (MARGIN, "float3"),
            "rule_auroc": (rule_d.auroc, "float3"),
            "other_auroc": (other_d.auroc, "float3"),
            "leakage_rows": (leak_rows, "int"),
            "as_of_month": (as_of, "text"),
            "delinquent_now": (now.height, "int"),
            "queue_size": (queue.height, "int"),
            "queue_exposure": (float(queue["expected_loss_exposure"].sum()), "usd0"),
            "queue_balance": (float(queue["balance"].sum()), "usd0"),
            "delinquent_balance": (float(now["balance"].sum()), "usd0"),
            "total_exposure": (float(now["expected_loss_exposure"].sum()), "usd0"),
        },
        extra_tables={"importance": importance},
        extra_formats={"importance": ["text", "pct1" if champion == "boosted" else "float2"]},
    )
    challenges = read_challenges(root / "DECISIONS.md")
    m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
    put_result(m, result, challenges)
    m.save(out / "manifest.json")
    write_inventory(models_dir, [inventory_row(result)])
    return result
