"""fraud_account: application fraud on the BAF suite, measured under the suite's own fairness protocol.

The Bank Account Fraud suite (Jesus et al., NeurIPS 2022) is a set of synthetic bank
account opening applications generated from a real fraud dataset, published with the
protected attributes kept so that fairness can be measured. Its protocol, reproduced
here: the first months train and months 6 and 7 test; the headline measure is recall at
a five percent false positive rate; fairness is predictive equality, the ratio of the
false positive rates of applicants aged fifty and over and the rest at that threshold.

Two variants side by side, a 300,000 row sample of each: the base, and variant II,
where the two age groups are about the same size and the older group's fraud rate is
much further above the younger group's.

One deviation, stated in the report: the suite trains on months 0 to 5. Here month 5
is held back to choose the tree count and the threshold a bank could actually deploy,
so the model trains on months 0 to 4.

Age is measured and never used. customer_age is on the proxy list and the feature list
is checked against it. How much the remaining features know about age anyway is
measured, and a search for a less discriminatory alternative drops the features that
carry the most age, one at a time, and publishes what each step costs in recall.
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
from ledger_scorecard.policy_files import load_proxies
from ledger_scorecard.scorecard import check_proxies
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import (
    confusion_at,
    discrimination,
    predictive_equality,
    recall_at_fpr,
    reliability,
    subgroup_table,
)
from ledger_models.gates import Gate, run_gates
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory

MODEL_ID = "fraud_account"
VARIANTS = {"base": "Base", "variant_ii": "Variant II"}
TARGET_FPR = 0.05
OLDER = 50
TRAIN_MONTHS = (0, 4)
VALIDATION_MONTH = 5
TEST_MONTHS = (6, 7)
CATEGORICAL = ("payment_type", "employment_status", "housing_status", "source", "device_os")
NUMERIC = (
    "income",
    "prev_address_months_count",
    "current_address_months_count",
    "days_since_request",
    "intended_balcon_amount",
    "zip_count_4w",
    "velocity_6h",
    "velocity_24h",
    "velocity_4w",
    "bank_branch_count_8w",
    "credit_risk_score",
    "email_is_free",
    "phone_home_valid",
    "phone_mobile_valid",
    "bank_months_count",
    "has_other_cards",
    "proposed_credit_limit",
    "foreign_request",
    "session_length_in_minutes",
    "keep_alive_session",
    "device_distinct_emails_8w",
    "device_fraud_count",
)
FEATURES = (*NUMERIC, *CATEGORICAL)
# The suite marks a missing value with a negative number in these fields.
MISSING_AS_NEGATIVE = (
    "prev_address_months_count",
    "current_address_months_count",
    "intended_balcon_amount",
    "bank_months_count",
    "session_length_in_minutes",
    "device_distinct_emails_8w",
)
# How many of the strongest age carriers the alternative search removes, cumulatively.
ALTERNATIVE_STEPS = 3


def params(seed: int) -> dict[str, Any]:
    return {
        "objective": "binary",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 4,
        "verbose": -1,
    }


def load(con: duckdb.DuckDBPyConnection, variant: str) -> pl.DataFrame:
    # No order by: the rows come back in file order, which is fixed. Sorting on month alone
    # would leave ties in whatever order the parallel sort produced, and bagging depends on it.
    frame = con.execute("select * from staging.stg_baf where variant = ?", [variant]).pl()
    return frame.with_columns([pl.col(c).cast(pl.Utf8) for c in CATEGORICAL])


def split(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    month = pl.col("month")
    return (
        frame.filter(month.is_between(*TRAIN_MONTHS)),
        frame.filter(month == VALIDATION_MONTH),
        frame.filter(month.is_between(*TEST_MONTHS)),
    )


def _pandas(frame: pl.DataFrame, features: list[str], levels: dict[str, list[str]]) -> Any:
    """The LightGBM input: numeric columns as they are, categoricals with fixed levels."""
    import pandas as pd

    out = frame.select(features).to_pandas()
    for c in features:
        if c in levels:
            out[c] = pd.Categorical(out[c], categories=levels[c])
    return out


def fit_booster(
    train: pl.DataFrame,
    val: pl.DataFrame,
    features: list[str],
    target: str,
    levels: dict[str, list[str]],
    seed: int,
    rounds: int = 1000,
) -> lgb.Booster:
    dtrain = lgb.Dataset(_pandas(train, features, levels), train[target].to_numpy(), free_raw_data=False)
    dval = lgb.Dataset(_pandas(val, features, levels), val[target].to_numpy(), reference=dtrain)
    return lgb.train(
        params(seed),
        dtrain,
        num_boost_round=rounds,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )


def predict(
    booster: lgb.Booster, frame: pl.DataFrame, features: list[str], levels: dict[str, list[str]]
) -> np.ndarray:
    return np.asarray(booster.predict(_pandas(frame, features, levels), num_iteration=booster.best_iteration))


def logistic_design(frame: pl.DataFrame, levels: dict[str, list[str]]) -> np.ndarray:
    """One hot categoricals, a flag and a zero for each missing marker, everything else as it is."""
    cols = []
    for c in NUMERIC:
        values = frame[c].cast(pl.Float64).to_numpy()
        if c in MISSING_AS_NEGATIVE:
            missing = values < 0
            cols.append(missing.astype(float))
            values = np.where(missing, 0.0, values)
        cols.append(values)
    for c in CATEGORICAL:
        for level in levels[c][1:]:
            cols.append((frame[c] == level).cast(pl.Float64).to_numpy())
    return np.column_stack(cols)


def older(frame: pl.DataFrame) -> np.ndarray:
    return frame["customer_age"].to_numpy() >= OLDER


def age_band(frame: pl.DataFrame) -> np.ndarray:
    age = frame["customer_age"].to_numpy()
    bands = np.select(
        [age < 30, age < 40, age < 50, age < 60],
        ["under 30", "30 to 39", "40 to 49", "50 to 59"],
        default="60 and over",
    )
    return np.asarray(bands)


def age_carriers(
    train: pl.DataFrame, val: pl.DataFrame, test: pl.DataFrame, levels: dict[str, list[str]], seed: int
) -> tuple[float, list[str]]:
    """How well the model's own features predict age fifty and over, and which carry it most."""
    frame = [
        f.with_columns(older=(pl.col("customer_age") >= OLDER).cast(pl.Int8)) for f in (train, val, test)
    ]
    booster = fit_booster(frame[0], frame[1], list(FEATURES), "older", levels, seed, rounds=400)
    auc = float(
        roc_auc_score(frame[2]["older"].to_numpy(), predict(booster, frame[2], list(FEATURES), levels))
    )
    gain = booster.feature_importance("gain")
    ranked = [name for name, _ in sorted(zip(FEATURES, gain, strict=True), key=lambda t: -t[1])]
    return auc, ranked


def protocol(
    y: np.ndarray, p: np.ndarray, is_older: np.ndarray, threshold: float | None = None
) -> dict[str, float]:
    """The suite's measures. With no threshold given it is set on these rows at the target rate."""
    if threshold is None:
        recall, threshold = recall_at_fpr(y, p, TARGET_FPR)
    else:
        recall = float((p[y == 1] >= threshold).mean())
    c = confusion_at(y, p, threshold)
    fpr_old, fpr_young, ratio = predictive_equality(y, p, is_older, threshold)
    return {
        "threshold": threshold,
        "recall": recall,
        "fpr": c["fpr"],
        "precision": c["precision"],
        "fpr_older": fpr_old,
        "fpr_younger": fpr_young,
        "ratio": ratio,
    }


def evaluate_variant(con: duckdb.DuckDBPyConnection, variant: str, seed: int) -> dict[str, Any]:
    frame = load(con, variant)
    train, val, test = split(frame)
    levels = {c: sorted(train[c].unique().to_list()) for c in CATEGORICAL}
    booster = fit_booster(train, val, list(FEATURES), "fraud_bool", levels, seed)
    y = {
        name: part["fraud_bool"].to_numpy().astype(float)
        for name, part in (("train", train), ("val", val), ("test", test))
    }
    p_train = predict(booster, train, list(FEATURES), levels)
    p_val = predict(booster, val, list(FEATURES), levels)
    p_test = predict(booster, test, list(FEATURES), levels)
    old_val, old_test = older(val), older(test)

    suite = protocol(y["test"], p_test, old_test)
    # The threshold a bank could deploy: fixed on month 5, then applied to months 6 and 7.
    fixed = protocol(y["val"], p_val, old_val)
    deployed = protocol(y["test"], p_test, old_test, threshold=fixed["threshold"])

    scaler = StandardScaler()
    logit = LogisticRegression(max_iter=5000, C=1.0)
    logit.fit(scaler.fit_transform(logistic_design(train, levels)), y["train"])
    p_logit = logit.predict_proba(scaler.transform(logistic_design(test, levels)))[:, 1]
    logit_suite = protocol(y["test"], p_logit, old_test)

    age_auc, carriers = age_carriers(train, val, test, levels, seed)
    alternatives = [
        {"removed": "Nothing (the model)", **suite, "auroc": float(roc_auc_score(y["test"], p_test))}
    ]
    for k in range(1, ALTERNATIVE_STEPS + 1):
        kept = [f for f in FEATURES if f not in carriers[:k]]
        alt = fit_booster(train, val, kept, "fraud_bool", levels, seed)
        p_alt = predict(alt, test, kept, levels)
        alternatives.append(
            {
                "removed": ", ".join(carriers[:k]),
                **protocol(y["test"], p_alt, old_test),
                "auroc": float(roc_auc_score(y["test"], p_alt)),
            }
        )

    older_share = float(older(frame).mean())
    rate_old = float(frame.filter(pl.col("customer_age") >= OLDER)["fraud_bool"].mean())  # type: ignore[arg-type]
    rate_young = float(frame.filter(pl.col("customer_age") < OLDER)["fraud_bool"].mean())  # type: ignore[arg-type]
    return {
        "variant": variant,
        "booster": booster,
        "levels": levels,
        "rows": frame.height,
        "train": train,
        "val": val,
        "test": test,
        "y": y,
        "p": {"train": p_train, "val": p_val, "test": p_test},
        "p_logit": p_logit,
        "suite": suite,
        "fixed": fixed,
        "deployed": deployed,
        "logit_suite": logit_suite,
        "age_auc": age_auc,
        "carriers": carriers,
        "alternatives": alternatives,
        "older_share": older_share,
        "rate_older": rate_old,
        "rate_younger": rate_young,
    }


def univariate_screen(train: pl.DataFrame, test: pl.DataFrame) -> tuple[float, str]:
    """The strongest single feature's test AUROC, either direction: a feature computed after the
    outcome would predict it almost alone. Categoricals score by their training fraud rate."""
    y = test["fraud_bool"].to_numpy()
    best, name = 0.5, ""
    for c in FEATURES:
        if c in CATEGORICAL:
            rates = dict(train.group_by(c).agg(pl.col("fraud_bool").mean()).iter_rows())
            score = np.array([rates.get(v, 0.0) for v in test[c].to_list()])
        else:
            score = test[c].cast(pl.Float64).to_numpy()
        auc = float(roc_auc_score(y, score))
        auc = max(auc, 1 - auc)
        if auc > best:
            best, name = auc, c
    return best, name


def variant_table(results: list[dict[str, Any]]) -> pl.DataFrame:
    rows: list[tuple[str, str, str]] = [
        ("Applications in the sample", "rows", "int"),
        ("Share aged fifty and over", "older_share", "pct1"),
        ("Fraud rate, aged fifty and over", "rate_older", "pct2"),
        ("Fraud rate, under fifty", "rate_younger", "pct2"),
        ("Test AUROC", "auroc", "float3"),
        ("Recall at a five percent false positive rate (the suite's measure)", "suite.recall", "pct1"),
        ("False positive rate, aged fifty and over", "suite.fpr_older", "pct2"),
        ("False positive rate, under fifty", "suite.fpr_younger", "pct2"),
        ("Predictive equality (lower rate over higher)", "suite.ratio", "float2"),
        ("Logistic benchmark: recall at the same rate", "logit_suite.recall", "pct1"),
        ("Threshold fixed on month five: recall on the test months", "deployed.recall", "pct1"),
        ("Threshold fixed on month five: false positive rate on the test months", "deployed.fpr", "pct2"),
        ("Threshold fixed on month five: predictive equality", "deployed.ratio", "float2"),
        ("AUROC of the features at predicting age fifty and over", "age_auc", "float3"),
    ]

    def get(r: dict[str, Any], key: str) -> float:
        if key == "auroc":
            return float(roc_auc_score(r["y"]["test"], r["p"]["test"]))
        if "." in key:
            a, b = key.split(".")
            return float(r[a][b])
        return float(r[key])

    return pl.DataFrame(
        {
            "measure": [label for label, _, _ in rows],
            "format": [fmt for _, _, fmt in rows],
            **{VARIANTS[r["variant"]]: [get(r, key) for _, key, _ in rows] for r in results},
        }
    )


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> ModelResult:
    out = models_dir / MODEL_ID
    out.mkdir(parents=True, exist_ok=True)
    proxies = load_proxies(root / "rules")
    check_proxies(list(FEATURES), proxies)
    seed = cfg.seed % 100_000

    results = [evaluate_variant(con, variant, seed) for variant in VARIANTS]
    base, biased = results
    y, p = base["y"], base["p"]
    samples = {
        "development": discrimination(y["train"], p["train"]),
        "validation": discrimination(y["val"], p["val"]),
        "test": discrimination(y["test"], p["test"]),
    }
    baselines = {
        "Base rate": discrimination(y["test"], np.full(y["test"].size, float(y["train"].mean()))),
        "Logistic on the same features": discrimination(y["test"], base["p_logit"]),
    }
    screen_auc, screen_feature = univariate_screen(base["train"], base["test"])
    suite, deployed = base["suite"], base["deployed"]
    gates = [
        Gate("auroc", "Test AUROC at or above the floor", "at_least", 0.80),
        Gate(
            "recall_deployed",
            "Test recall at the threshold fixed on month five",
            "at_least",
            0.40,
        ),
        Gate(
            "vs_logistic",
            "Recall at a five percent false positive rate above the logistic benchmark",
            "at_least",
            0.0,
        ),
        Gate(
            "fpr_drift",
            "Test false positive rate at the threshold fixed on month five",
            "at_most",
            0.075,
            critical=False,
        ),
        Gate(
            "screen",
            "Strongest single feature's test AUROC (a feature known after the outcome would stand alone)",
            "at_most",
            0.80,
        ),
        Gate(
            "predictive_equality",
            "Predictive equality between the age groups at the suite's threshold",
            "at_least",
            0.80,
            critical=False,
        ),
        Gate("ece", "Expected calibration error on test", "at_most", 0.01, critical=False),
    ]
    measured = {
        "auroc": samples["test"].auroc,
        "recall_deployed": deployed["recall"],
        "vs_logistic": suite["recall"] - base["logit_suite"]["recall"],
        "fpr_drift": deployed["fpr"],
        "screen": screen_auc,
        "predictive_equality": suite["ratio"],
        "ece": samples["test"].ece,
    }
    tier, tier_reason = tier_for(decides_automatically=False, informs_person=True, complex_method=True)
    card = ModelCard(
        model_id=MODEL_ID,
        function="f04",
        title="Application fraud on the BAF suite",
        purpose="Score a bank account application for fraud when it is submitted, so that the riskiest ask for documents before the account opens",
        tier=tier,
        tier_reason=tier_reason,
        role="sole",
        status="in use",
        prediction_time="When the application is submitted; the suite's features describe the application and the activity before it",
        outcome="The application was fraudulent, as the suite labels it",
        population="Bank account applications in the BAF suite's base variant, a 300,000 sample; variant II beside it",
        backend="real:baf",
        method="LightGBM on the suite's application features, early stopped on month five; no protected attribute or listed proxy",
        features=list(FEATURES),
        lines={
            "trained": "On months 0 to 4 of the base variant; month 5 chooses the tree count and the deployable threshold.",
            "timed": "The suite computes its features at application time and ships no raw history to recompute them from, so the split is temporal and a single feature screen looks for anything known only after the outcome.",
            "calibrated": "Reliability on the test months is published; the threshold is set by false positive rate, so the score is used as a rank.",
            "useful": "Beats the base rate and a logistic model on the same features at the suite's own measure, recall at a five percent false positive rate.",
            "fair": "Predictive equality between applicants aged fifty and over and the rest, on both variants, with a search for a less discriminatory alternative published beside it.",
            "gated": "Every gate in this report, including the recall at a threshold fixed before the test months.",
            "served": "Scored in the pipeline; not served by the API, because no live application stream exists here.",
            "integrated": "An application at or above the threshold asks for documents before the account opens. The model never declines one.",
            "monitored": "Monthly false positive rate against the threshold, by age group; recall on labelled applications; score PSI.",
            "documented": "This validation report and the desk page's fairness audit.",
            "bounded": "Routes applications to document checks only; never declines, never prices, and never sees age.",
            "validated": "This report, rendered from the manifest before the threshold is used.",
            "explainable": "A routed application shows the features that moved its score most, in the suite's own terms.",
        },
    )
    bands = ["under 30", "30 to 39", "40 to 49", "50 to 59", "60 and over"]
    subgroups = subgroup_table(
        y["test"], p["test"], age_band(base["test"]), threshold=suite["threshold"]
    ).sort(pl.col("group").replace_strict({b: i for i, b in enumerate(bands)}, return_dtype=pl.Int64))
    alternatives = pl.concat(
        [
            pl.DataFrame(r["alternatives"]).with_columns(variant=pl.lit(VARIANTS[r["variant"]]))
            for r in results
        ]
    ).select("variant", "removed", "auroc", "recall", "fpr_older", "fpr_younger", "ratio")
    variants = variant_table(results)
    result = ModelResult(
        card=card,
        samples=samples,
        baselines=baselines,
        gates=run_gates(gates, measured),
        reliability=reliability(y["test"], p["test"]),
        subgroups=subgroups,
        monitoring=[
            (
                "False positive rate at the threshold, monthly, by age group",
                f"overall above {TARGET_FPR * 1.5:.1%} or the ratio below its validated value",
                "Reset the threshold on the latest labelled month",
            ),
            (
                "Recall on labelled applications, monthly",
                "below the validated recall for two months",
                "Revalidate",
            ),
            ("Score PSI, monthly against month five", f"above {cfg.model_risk.psi_breach:g}", "Revalidate"),
        ],
        last_validated=cfg.calendar.as_of.isoformat(),
        extra_values={
            "rows": (base["rows"], "int"),
            "train_months": ("months 0 to 4", "text"),
            "validation_month": ("month 5", "text"),
            "test_months": ("months 6 and 7", "text"),
            "suite_train_months": ("months 0 to 5", "text"),
            "target_fpr": (TARGET_FPR, "pct0"),
            "older_age": (OLDER, "int"),
            "recall_suite": (suite["recall"], "pct1"),
            "threshold_suite": (suite["threshold"], "float4"),
            "fpr_older": (suite["fpr_older"], "pct2"),
            "fpr_younger": (suite["fpr_younger"], "pct2"),
            "fpr_times": (suite["fpr_older"] / suite["fpr_younger"], "float1"),
            "ratio": (suite["ratio"], "float2"),
            "recall_deployed": (deployed["recall"], "pct1"),
            "fpr_deployed": (deployed["fpr"], "pct2"),
            "ratio_deployed": (deployed["ratio"], "float2"),
            "threshold_deployed": (base["fixed"]["threshold"], "float4"),
            "recall_logistic": (base["logit_suite"]["recall"], "pct1"),
            "age_auc": (base["age_auc"], "float3"),
            "carriers": (", ".join(base["carriers"][:ALTERNATIVE_STEPS]), "text"),
            "screen_auc": (screen_auc, "float3"),
            "screen_feature": (screen_feature, "text"),
            "trees": (base["booster"].best_iteration, "int"),
            "ii_rows": (biased["rows"], "int"),
            "ii_recall_suite": (biased["suite"]["recall"], "pct1"),
            "ii_ratio": (biased["suite"]["ratio"], "float2"),
            "ii_fpr_older": (biased["suite"]["fpr_older"], "pct2"),
            "ii_fpr_younger": (biased["suite"]["fpr_younger"], "pct2"),
            "ii_age_auc": (biased["age_auc"], "float3"),
            "ii_older_share": (biased["older_share"], "pct1"),
            "base_older_share": (base["older_share"], "pct1"),
            "base_prevalence_times": (base["rate_older"] / base["rate_younger"], "float1"),
            "ii_prevalence_times": (biased["rate_older"] / biased["rate_younger"], "float1"),
            "alt_best_ratio": (max(r["ratio"] for r in base["alternatives"]), "float2"),
            "alt_last_recall": (base["alternatives"][-1]["recall"], "pct1"),
            "alt_last_ratio": (base["alternatives"][-1]["ratio"], "float2"),
        },
        extra_tables={"alternatives": alternatives},
        extra_formats={"alternatives": ["text", "text", "float3", "pct1", "pct2", "pct2", "float2"]},
    )
    challenges = read_challenges(root / "DECISIONS.md")
    m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
    put_result(m, result, challenges)
    # The side by side table with each row in its own format, for the report and the page.
    m.put_table(
        f"models.{MODEL_ID}.variants",
        ["Measure", *VARIANTS.values()],
        ["text", "text", "text"],
        [
            [row["measure"], *(_fmt_cell(row[name], row["format"]) for name in VARIANTS.values())]
            for row in variants.iter_rows(named=True)
        ],
        backend="real:baf",
        population=card.population,
        source=f"packages/models ({MODEL_ID})",
    )
    m.save(out / "manifest.json")
    write_inventory(models_dir, [inventory_row(result)])
    base["booster"].save_model(str(out / "model.txt"), num_iteration=base["booster"].best_iteration)
    alternatives.write_parquet(out / "alternatives.parquet")
    variants.write_parquet(out / "variants.parquet")
    subgroups.write_parquet(out / "age_bands.parquet")
    return result


def _fmt_cell(value: float, fmt: str) -> str:
    from ledger_core.formats import format_value

    return format_value(value, fmt)
