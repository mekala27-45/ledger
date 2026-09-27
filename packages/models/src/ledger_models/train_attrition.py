"""attrition: will this customer close their primary checking account within twelve months?

At each month end, the probability that a customer's checking account closes in the
next twelve months, from what the bank knew at that month end. It is integrated into a
retention list ranked by expected balance at risk: the probability times the balances
the customer holds, so a call goes to the relationship worth keeping.

A twelve month outcome is only known twelve months later. The split respects that: the
model a bank could have fitted on 31 May 2025 trains on month ends whose windows had
closed by then, and is tested on the month ends of June to August 2025, whose outcomes
were all known by the as of date.
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
from sklearn.preprocessing import StandardScaler

from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import discrimination, reliability, subgroup_table
from ledger_models.gates import Gate, run_gates
from ledger_models.reasons import Words, reasons
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory

MODEL_ID = "attrition"
TRAIN = ("2023-09", "2024-02")
VALIDATION = ("2024-03", "2024-05")
TEST = ("2025-06", "2025-08")
FEATURES = (
    "log_checking_balance",
    "log_other_balance",
    "has_other",
    "change_3m",
    "change_3m_missing",
    "balance_drop",
    "fee_count",
    "overdraft_count",
    "log_inflow",
    "log_outflow",
    "entries",
    "payroll_credits",
    "tenure_months",
    "new_customer",
    "digital_active",
    "complaint_flag",
    "rate_gap",
    "log_income",
)
FEATURE_WORDS: dict[str, Words] = {
    "log_checking_balance": "checking balance",
    "log_other_balance": "savings and time balances",
    "has_other": ("holds savings or a CD", "holds no savings or CD"),
    "change_3m": "checking balance change over three months",
    "change_3m_missing": ("less than three months of history", None),
    "balance_drop": ("checking balance fell sharply last month", None),
    "fee_count": "fees charged last month",
    "overdraft_count": "overdraft last month",
    "log_inflow": "money coming in",
    "log_outflow": "money going out",
    "entries": "account activity",
    "payroll_credits": "payroll deposits",
    "tenure_months": "time as a customer",
    "new_customer": ("customer for under a year", None),
    "digital_active": ("uses digital banking", "does not use digital banking"),
    "complaint_flag": ("has complained", None),
    "rate_gap": "savings rate far below market",
    "log_income": "income",
}
TOP_SHARE = 0.10
# How much better, in validation AUROC on held out customers, the boosted model must be to be chosen.
MARGIN = 0.005
RETENTION_LIST = 500


def outcomes_known_before(last_fit_month: str, first_test_month: str, horizon_months: int = 12) -> bool:
    """True when every outcome window of the fitting months closed by the first test month end.

    The outcome for month end t covers months t + 1 to t + horizon, so it is known at the end
    of month t + horizon and may be used by a model that scores month T only if T - t >= horizon.
    """
    fy, fm = (int(x) for x in last_fit_month.split("-"))
    ty, tm = (int(x) for x in first_test_month.split("-"))
    return (ty * 12 + tm) - (fy * 12 + fm) >= horizon_months


def _label(words: Words) -> str:
    return words if isinstance(words, str) else words[0]


def load(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Customer month features, point in time, joined to the static facts known at opening."""
    frame = con.execute(
        """
        with m as (
            select cm.*,
                lag(cm.checking_balance) over (partition by cm.customer_id order by cm.month_index) as prev_balance
            from marts.mart_customer_month cm
        )
        select m.customer_id, m.month, m.month_index, m.checking_balance::double as checking_balance,
            m.other_balance::double as other_balance, m.checking_change_3m::double as checking_change_3m,
            m.prev_balance::double as prev_balance, m.fee_count, m.overdraft_count, m.inflow::double as inflow,
            m.outflow::double as outflow, m.entries, m.payroll_credits, m.checking_tenure_months,
            m.closes_within_12m, c.digital_active, c.complaint_flag, c.annual_income::double as annual_income,
            c.birth_year, r.policy_rate, r.savings_rate
        from m
        join marts.dim_customer c using (customer_id)
        join staging.stg_deposit_rates r using (month)
        order by m.month_index, m.customer_id
        """
    ).pl()
    return frame.with_columns(
        log_checking_balance=pl.col("checking_balance").clip(0, None).log1p(),
        log_other_balance=pl.col("other_balance").clip(0, None).log1p(),
        has_other=(pl.col("other_balance") > 0).cast(pl.Float64),
        change_3m=(pl.col("checking_change_3m").fill_null(0.0) / 1000.0).clip(-50, 50),
        change_3m_missing=pl.col("checking_change_3m").is_null().cast(pl.Float64),
        balance_drop=(
            pl.col("prev_balance").is_not_null()
            & (pl.col("checking_balance") < 0.6 * pl.max_horizontal(pl.col("prev_balance"), pl.lit(1.0)))
        ).cast(pl.Float64),
        fee_count=pl.col("fee_count").cast(pl.Float64),
        overdraft_count=pl.col("overdraft_count").cast(pl.Float64),
        log_inflow=pl.col("inflow").log1p(),
        log_outflow=pl.col("outflow").log1p(),
        entries=pl.col("entries").cast(pl.Float64),
        payroll_credits=pl.col("payroll_credits").cast(pl.Float64),
        tenure_months=pl.col("checking_tenure_months").cast(pl.Float64),
        new_customer=(pl.col("checking_tenure_months") < 12).cast(pl.Float64),
        digital_active=pl.col("digital_active").cast(pl.Float64),
        complaint_flag=pl.col("complaint_flag").cast(pl.Float64),
        rate_gap=(
            (pl.col("policy_rate") - pl.col("savings_rate") - 2.0).clip(0, None)
            * (pl.col("other_balance") > 0).cast(pl.Float64)
        ),
        log_income=pl.col("annual_income").log1p(),
        age=(pl.col("month").str.slice(0, 4).cast(pl.Int32) - pl.col("birth_year")),
        balance_total=pl.col("checking_balance").clip(0, None) + pl.col("other_balance").clip(0, None),
    )


def age_band(age: pl.Expr) -> pl.Expr:
    return (
        pl.when(age < 25)
        .then(pl.lit("under 25"))
        .when(age < 35)
        .then(pl.lit("25 to 34"))
        .when(age < 50)
        .then(pl.lit("35 to 49"))
        .when(age < 65)
        .then(pl.lit("50 to 64"))
        .otherwise(pl.lit("65 and over"))
    )


def part(frame: pl.DataFrame, window: tuple[str, str]) -> pl.DataFrame:
    return frame.filter(
        pl.col("month").is_between(pl.lit(window[0]), pl.lit(window[1]))
        & pl.col("closes_within_12m").is_not_null()
    )


def matrix(frame: pl.DataFrame, columns: tuple[str, ...] = FEATURES) -> np.ndarray:
    return frame.select(columns).to_numpy().astype(float)


def capture(y: np.ndarray, score: np.ndarray, weight: np.ndarray, share: float) -> tuple[float, float]:
    """Among the top ``share`` by score: the share of closers found and of their balances."""
    k = max(1, int(round(share * y.size)))
    top = np.argsort(-score, kind="stable")[:k]
    closers = y == 1
    found = float(y[top].sum() / max(y.sum(), 1))
    money = float((weight[top] * y[top]).sum() / max((weight * closers).sum(), 1e-9))
    return found, money


def oracle_auroc(con: duckdb.DuckDBPyConnection, root: Path, test: pl.DataFrame) -> float:
    """The ceiling: the generator's true monthly hazards over each twelve month window as a score.

    It knows the future (the hazards of months after the month end) and the generator's
    formula, so no model can reach it; it says how much separation the data holds at all.
    """
    from sklearn.metrics import roc_auc_score

    hazard = pl.read_parquet(root / "data" / "raw" / "truth" / "truth_attrition_hazard.parquet")
    checking = con.execute(
        "select account_id, customer_id from marts.dim_deposit_account where product = 'checking'"
    ).pl()
    months = sorted(hazard["month"].unique().to_list())
    index = {mo: i for i, mo in enumerate(months)}
    h = (
        hazard.join(checking, on="account_id")
        .with_columns(k=pl.col("month").replace_strict(index, return_dtype=pl.Int64))
        .select("customer_id", "k", "hazard")
    )
    rows = test.select("customer_id", "month", "closes_within_12m").with_columns(
        t=pl.col("month").replace_strict(index, return_dtype=pl.Int64)
    )
    joined = rows.join(h, on="customer_id").filter(
        (pl.col("k") > pl.col("t")) & (pl.col("k") <= pl.col("t") + 12)
    )
    # The mean hazard over the months the account was open, so a customer who left early is
    # not scored as safer for having fewer months to accumulate risk in.
    risk = joined.group_by("customer_id", "t").agg((1 - (1 - pl.col("hazard").mean()) ** 12).alias("oracle"))
    scored = rows.join(risk, on=["customer_id", "t"], how="left").with_columns(
        pl.col("oracle").fill_null(0.0)
    )
    return float(roc_auc_score(scored["closes_within_12m"].to_numpy(), scored["oracle"].to_numpy()))


def leakage_check(con: duckdb.DuckDBPyConnection, test: pl.DataFrame, seed: int) -> int:
    """Recompute the month's activity features for sampled rows from the posted entries."""
    sample = test.sample(n=min(400, test.height), seed=seed)
    history = con.execute(
        """
        select customer_id, posted_at, amount::double as amount, txn_type, product
        from marts.fct_deposit_entry where customer_id in (select unnest(?))
        """,
        [sample["customer_id"].unique().to_list()],
    ).pl()
    frame = sample.with_columns(
        prediction_at=(pl.col("month") + "-01").str.to_datetime("%Y-%m-%d").dt.offset_by("1mo"),
        month_start=(pl.col("month") + "-01").str.to_datetime("%Y-%m-%d"),
    )

    def recompute(past: pl.DataFrame, row: dict[str, Any]) -> dict[str, float]:
        window = past.filter(pl.col("posted_at") >= row["month_start"])
        checking = window.filter(pl.col("product") == "checking")
        fees = window.filter(pl.col("txn_type").is_in(["FEE_MAINTENANCE", "FEE_OVERDRAFT"]))
        inflow = float(checking.filter(pl.col("amount") > 0)["amount"].sum()) if checking.height else 0.0
        return {
            "fee_count": float(fees.height),
            "overdraft_count": float(fees.filter(pl.col("txn_type") == "FEE_OVERDRAFT").height),
            "entries": float(checking.height),
            "payroll_credits": float(checking.filter(pl.col("txn_type") == "PAYROLL_IN").height),
            "log_inflow": float(np.log1p(inflow)),
        }

    return recompute_check(
        frame,
        PointInTimeFrame.build(history, "customer_id", "posted_at"),
        "prediction_at",
        recompute,  # type: ignore[arg-type]
        ["fee_count", "overdraft_count", "entries", "payroll_credits", "log_inflow"],
        sample=200,
        seed=seed,
        tolerance=1e-6,
    )


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> ModelResult:
    out = models_dir / MODEL_ID
    out.mkdir(parents=True, exist_ok=True)
    check_proxies(list(FEATURES), load_proxies(root / "rules"))
    horizon = cfg.censoring.default_window_months
    if not outcomes_known_before(VALIDATION[1], TEST[0], horizon):
        raise ValueError(
            "an outcome used to fit or choose the model was not known by the first test month end"
        )
    seed = cfg.seed % 100_000
    frame = load(con)
    train, val, test = part(frame, TRAIN), part(frame, VALIDATION), part(frame, TEST)
    y = {
        n: f["closes_within_12m"].to_numpy().astype(float)
        for n, f in (("train", train), ("val", val), ("test", test))
    }
    # The same customers appear in every month, with the same income and tenure path, so a
    # validation sample of month ends alone lets trees memorise people and never stop. Early
    # stopping uses customers the fit never saw, and the leaves are kept large.
    held_out = (pl.col("customer_id").hash(seed) % 5) == 0
    fit_rows = train.filter(~held_out)
    stop_rows = val.filter(held_out)
    params = {
        "objective": "binary",
        "learning_rate": 0.03,
        "num_leaves": 15,
        "min_data_in_leaf": 1000,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 10.0,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 4,
        "verbose": -1,
    }
    dtrain = lgb.Dataset(
        matrix(fit_rows),
        fit_rows["closes_within_12m"].to_numpy().astype(float),
        feature_name=list(FEATURES),
        free_raw_data=False,
    )
    dval = lgb.Dataset(
        matrix(stop_rows), stop_rows["closes_within_12m"].to_numpy().astype(float), reference=dtrain
    )
    booster = lgb.train(
        params, dtrain, 1500, valid_sets=[dval], callbacks=[lgb.early_stopping(100, verbose=False)]
    )

    fit_y = fit_rows["closes_within_12m"].to_numpy().astype(float)
    scaler = StandardScaler().fit(matrix(fit_rows))
    logit = LogisticRegression(max_iter=5000).fit(scaler.transform(matrix(fit_rows)), fit_y)

    def boosted(f: pl.DataFrame) -> np.ndarray:
        return np.asarray(booster.predict(matrix(f), num_iteration=booster.best_iteration))

    def logistic(f: pl.DataFrame) -> np.ndarray:
        return np.asarray(logit.predict_proba(scaler.transform(matrix(f)))[:, 1])

    # The champion is chosen on validation customers neither fit saw. The boosted model has to
    # earn its complexity by a stated margin; otherwise the logistic regression is the model.
    from sklearn.metrics import roc_auc_score

    y_stop = stop_rows["closes_within_12m"].to_numpy().astype(float)
    auc_boosted = float(roc_auc_score(y_stop, boosted(stop_rows)))
    auc_logistic = float(roc_auc_score(y_stop, logistic(stop_rows)))
    champion = "boosted" if auc_boosted - auc_logistic >= MARGIN else "logistic"
    score, other = (boosted, logistic) if champion == "boosted" else (logistic, boosted)
    other_name = "Logistic on the same features" if champion == "boosted" else "LightGBM on the same features"

    p = {"train": score(train), "val": score(val), "test": score(test)}
    samples = {
        "development": discrimination(y["train"], p["train"]),
        "validation": discrimination(y["val"], p["val"]),
        "test": discrimination(y["test"], p["test"]),
    }
    p_other = other(test)
    logit_d = discrimination(y["test"], p_other)
    p_logit = p_other
    base = discrimination(y["test"], np.full(y["test"].size, float(y["train"].mean())))

    ceiling = oracle_auroc(con, root, test)

    money = test["balance_total"].to_numpy()
    found_p, money_p = capture(y["test"], p["test"], money, TOP_SHARE)
    found_ebr, money_ebr = capture(y["test"], p["test"] * money, money, TOP_SHARE)
    found_logit, _ = capture(y["test"], p_logit, money, TOP_SHARE)
    threshold = float(np.quantile(p["test"], 1 - TOP_SHARE))
    bands = test.select(age_band(pl.col("age")).alias("band"))["band"].to_numpy()
    order = ["under 25", "25 to 34", "35 to 49", "50 to 64", "65 and over"]
    subgroups = subgroup_table(y["test"], p["test"], bands, threshold=threshold).sort(
        pl.col("group").replace_strict({b: i for i, b in enumerate(order)}, return_dtype=pl.Int64)
    )
    flag_rates = [r for r in subgroups["flag_rate"].to_list() if r is not None]
    leak_rows = leakage_check(con, test, seed)

    gates = [
        Gate(
            "separation",
            "Share of the achievable separation reached: (AUROC minus one half) over (the ceiling minus one half)",
            "at_least",
            0.50,
        ),
        Gate(
            "vs_other",
            "Test AUROC against the other candidate's (the choice on validation must not cost more than a hundredth)",
            "at_least",
            -0.01,
        ),
        Gate("vs_base", "Test average precision above the base rate", "at_least", 0.0),
        Gate(
            "capture",
            "Share of closers in the top tenth of scores, test months (a tenth is no better than chance)",
            "at_least",
            0.15,
        ),
        Gate("leakage", "Point in time recompute of sampled customer months", "at_least", 200),
        Gate("ece", "Expected calibration error on test", "at_most", 0.02, critical=False),
    ]
    measured = {
        "separation": (samples["test"].auroc - 0.5) / (ceiling - 0.5),
        "vs_other": samples["test"].auroc - logit_d.auroc,
        "vs_base": samples["test"].average_precision - base.average_precision,
        "capture": found_p,
        "leakage": float(leak_rows),
        "ece": samples["test"].ece,
    }

    # The retention list on the as of month: expected balance at risk, with reasons.
    as_of = cfg.calendar.as_of.strftime("%Y-%m")
    now = frame.filter(pl.col("month") == as_of)
    p_now = score(now)
    now = now.with_columns(
        probability=pl.Series(p_now), expected_balance_at_risk=pl.Series(p_now) * pl.col("balance_total")
    ).sort("expected_balance_at_risk", descending=True)
    listed = now.head(RETENTION_LIST)
    if champion == "boosted":
        contrib = np.asarray(
            booster.predict(matrix(listed), num_iteration=booster.best_iteration, pred_contrib=True)
        )[:, :-1]
    else:
        contrib = scaler.transform(matrix(listed)) * logit.coef_[0]
    why = reasons(list(FEATURES), contrib, matrix(listed), FEATURE_WORDS, direction=1)
    listed = listed.with_columns(reasons=pl.Series(why)).select(
        "customer_id",
        "probability",
        "balance_total",
        "expected_balance_at_risk",
        "reasons",
    )
    listed.write_parquet(out / "retention_list.parquet")
    now.select(
        "customer_id", "month", "probability", "balance_total", "expected_balance_at_risk"
    ).write_parquet(out / "scores_as_of.parquet")

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
        function="f06",
        title="Deposit customer attrition, twelve month horizon",
        purpose="Rank customers by the balance the bank stands to lose if they leave in the next twelve months, so retention calls go where they are worth most",
        tier=tier,
        tier_reason=tier_reason,
        role="sole",
        status="in use",
        prediction_time="Each month end; features use only that month and earlier",
        outcome="The customer's primary checking account closes within the next twelve months",
        population="Harborline customers with an open checking account at a month end, September 2023 to August 2026",
        backend="generated",
        method=(
            "LightGBM on balances, flows, fees, tenure and product holding, early stopped on held out customers"
            if champion == "boosted"
            else "Logistic regression on balances, flows, fees, tenure and product holding, standardised; chosen over LightGBM on held out customers"
        ),
        features=list(FEATURES),
        lines={
            "trained": "On month ends September 2023 to February 2024, whose twelve month outcomes had all closed before the test months began.",
            "timed": "Every feature comes from the month end or earlier; a leakage test recomputes the month's activity for 200 sampled customer months from posted entries.",
            "calibrated": "Reliability on the test months is published, and the probability is used as a probability: it multiplies the balance.",
            "useful": "Beats the base rate, matches or beats the other candidate on months it never saw, and reaches a stated share of the separation the generator's own hazards reach.",
            "fair": "Flag rate and capture by age band at the top tenth. Age never enters the model.",
            "gated": "Every gate in this report.",
            "served": "Scored monthly in the pipeline; the retention list is published with the deposits page.",
            "integrated": "Orders the retention list by expected balance at risk: probability times the balances held.",
            "monitored": "Monthly score PSI; capture of the list against closures as they happen; closure rate by age band.",
            "documented": "This validation report and the deposits page.",
            "bounded": "Chooses whom to call. Never changes a price, a fee or an account, and never goes to a customer as a score.",
            "validated": "This report, rendered from the manifest before the list is used.",
            "explainable": "Each customer on the list shows the two features that raised the probability most, in plain words.",
        },
    )
    result = ModelResult(
        card=card,
        samples=samples,
        baselines={"Base rate": base, other_name: logit_d},
        gates=run_gates(gates, measured),
        reliability=reliability(y["test"], p["test"]),
        subgroups=subgroups,
        monitoring=[
            ("Score PSI, monthly against validation", f"above {cfg.model_risk.psi_breach:g}", "Revalidate"),
            (
                "Share of the list's customers who close within twelve months",
                "below the test capture for two quarters",
                "Refit",
            ),
            ("Flag rate by age band", "any band below half the highest", "Review the features"),
        ],
        last_validated=cfg.calendar.as_of.isoformat(),
        extra_values={
            "train_period": ("month ends September 2023 to February 2024", "text"),
            "validation_period": ("month ends March to May 2024", "text"),
            "test_period": ("month ends June to August 2025", "text"),
            "test_rows": (test.height, "int"),
            "test_closers": (int(y["test"].sum()), "int"),
            "top_share": (TOP_SHARE, "pct0"),
            "capture": (found_p, "pct1"),
            "capture_other": (found_logit, "pct1"),
            "money_by_probability": (money_p, "pct1"),
            "money_by_expected_balance": (money_ebr, "pct1"),
            "found_by_expected_balance": (found_ebr, "pct1"),
            "leakage_rows": (leak_rows, "int"),
            "trees": (booster.best_iteration, "int"),
            "champion": ("LightGBM" if champion == "boosted" else "logistic regression", "text"),
            "other": ("logistic regression" if champion == "boosted" else "LightGBM", "text"),
            "auc_boosted_holdout": (auc_boosted, "float3"),
            "auc_logistic_holdout": (auc_logistic, "float3"),
            "margin": (MARGIN, "float3"),
            "other_auroc": (logit_d.auroc, "float3"),
            "ceiling": (ceiling, "float3"),
            "separation": ((samples["test"].auroc - 0.5) / (ceiling - 0.5), "pct0"),
            "fit_customers_share": (0.8, "pct0"),
            "flag_ratio_age": (min(flag_rates) / max(flag_rates) if flag_rates else None, "float2"),
            "as_of_month": (as_of, "text"),
            "customers_scored": (now.height, "int"),
            "list_size": (listed.height, "int"),
            "list_expected_balance": (float(listed["expected_balance_at_risk"].sum()), "usd0"),
            "list_balances": (float(listed["balance_total"].sum()), "usd0"),
            "portfolio_expected_balance": (float(now["expected_balance_at_risk"].sum()), "usd0"),
            "mean_probability_now": (float(p_now.mean()), "pct1"),
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
