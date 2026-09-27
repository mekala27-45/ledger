"""aml_triage: which alert should an investigator open first.

The transaction monitoring rules fire alerts; this model ranks them by the chance an
alert is a real typology rather than a legitimate customer who looks like one. It is
trained on the generator's injected truth with a temporal split, integrated as the
sort order of the case queue, and documented under the model contract.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest
from ledger_core.pit import PointInTimeFrame, recompute_check
from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import discrimination, reliability
from ledger_models.gates import Gate, run_gates
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory
from ledger_scorecard.policy_files import load_proxies
from ledger_scorecard.scorecard import check_proxies
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ledger_crime.evaluate import label_alerts, posted_truth, scorecard
from ledger_crime.rules import AmlParams, run_rules
from ledger_crime.triage import FEATURES, build_features, recompute_history

MODEL_ID = "aml_triage"
TRAIN_END = datetime(2025, 9, 1)
VALIDATION_END = datetime(2026, 3, 1)
ABLATED = ("prior_cash_90d", "branches")


def params_from(cfg: LedgerConfig) -> AmlParams:
    a = cfg.aml
    return AmlParams(
        reporting_threshold=a.reporting_threshold,
        structuring_floor=a.structuring_floor,
        structuring_window_days=a.structuring_window_days,
        rapid_movement_hours=a.rapid_movement_hours,
        mule_fan_in_min_counterparties=a.mule_fan_in_min_counterparties,
        mule_window_days=a.mule_window_days,
        cycle_max_length=a.cycle_max_length,
        cycle_window_days=a.cycle_window_days,
    )


def split(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        split=pl.when(pl.col("end_at") < TRAIN_END)
        .then(pl.lit("development"))
        .when(pl.col("end_at") < VALIDATION_END)
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
    )


def _y(frame: pl.DataFrame) -> np.ndarray:
    return frame["true_positive"].cast(pl.Int8).to_numpy()


def fit(frame: pl.DataFrame, columns: tuple[str, ...]) -> tuple[StandardScaler, LogisticRegression]:
    x = frame.select(columns).to_numpy().astype(float)
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=1.0, max_iter=5000).fit(scaler.transform(x), _y(frame))
    return scaler, model


def score(
    frame: pl.DataFrame, columns: tuple[str, ...], fitted: tuple[StandardScaler, LogisticRegression]
) -> np.ndarray:
    scaler, model = fitted
    return np.asarray(
        model.predict_proba(scaler.transform(frame.select(columns).to_numpy().astype(float)))[:, 1]
    )


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> ModelResult:
    out = models_dir / MODEL_ID
    out.mkdir(parents=True, exist_ok=True)
    p = params_from(cfg)
    alerts = run_rules(con, p, root / "rules")
    truth = posted_truth(con, pl.read_parquet(root / "data" / "raw" / "truth" / "truth_typologies.parquet"))
    labelled = label_alerts(alerts, truth)
    frame = split(build_features(con, labelled))
    check_proxies(list(FEATURES), load_proxies(root / "rules"))

    dev = frame.filter(pl.col("split") == "development")
    val = frame.filter(pl.col("split") == "validation")
    test = frame.filter(pl.col("split") == "test")
    fitted = fit(dev, FEATURES)
    scores = {
        name: score(part, FEATURES, fitted)
        for name, part in (("development", dev), ("validation", val), ("test", test))
    }
    samples = {
        name: discrimination(_y(part), scores[name])
        for name, part in (("development", dev), ("validation", val), ("test", test))
    }

    # Baselines: the base rate, and the order the rules alone imply (each rule's development precision).
    rule_precision = dev.group_by("rule").agg(pl.col("true_positive").mean().alias("rp"))
    by_rule = (
        test.join(rule_precision, on="rule", how="left")["rp"].fill_null(float(_y(dev).mean())).to_numpy()
    )
    base = discrimination(_y(test), np.full(test.height, float(_y(dev).mean())))
    rule_order = discrimination(_y(test), by_rule)
    # The ablation: without the two features the generator made most different.
    kept = tuple(c for c in FEATURES if c not in ABLATED)
    ablated = discrimination(_y(test), score(test, kept, fit(dev, kept)))
    structuring = test.filter(pl.col("rule") == "structuring")
    s_scores = score(structuring, FEATURES, fitted)
    s_disc = discrimination(_y(structuring), s_scores)
    s_rule = discrimination(_y(structuring), np.full(structuring.height, 0.5))

    # The leakage test: recompute the history features for sampled alerts from raw entries.
    sample_accounts = frame["account_id"].unique().to_list()
    history = con.execute(
        """
        select account_id, posted_at, amount::double as amount, txn_type
        from marts.fct_deposit_entry where account_id in (select unnest(?))
        """,
        [sample_accounts],
    ).pl()
    leak_rows = recompute_check(
        frame.select("alert_id", "account_id", "start_at", "prior_cash_90d", "log_prior_inflow_90d"),
        PointInTimeFrame.build(history, "account_id", "posted_at"),
        "start_at",
        recompute_history,
        ["prior_cash_90d", "log_prior_inflow_90d"],
        sample=200,
        seed=cfg.seed % 10_000,
        tolerance=1e-6,
    )

    coef = dict(zip(FEATURES, fitted[1].coef_[0], strict=True))
    top_features = sorted(coef, key=lambda c: -abs(coef[c]))[:4]

    gates = [
        Gate("auroc", "Test AUROC at or above the floor", "at_least", 0.80),
        Gate("vs_rules", "Test average precision above the rules' own order", "at_least", 0.0),
        Gate(
            "structuring",
            "Test AUROC within structuring alerts, where the rules' order says nothing",
            "at_least",
            0.80,
        ),
        Gate("leakage", "Point in time recompute of sampled alerts", "at_least", 200),
        Gate("ece", "Expected calibration error on test", "at_most", 0.10, critical=False),
        Gate(
            "ablation",
            "Test AUROC without the cash history and branch count features",
            "at_least",
            0.75,
            critical=False,
        ),
    ]
    measured = {
        "auroc": samples["test"].auroc,
        "vs_rules": samples["test"].average_precision - rule_order.average_precision,
        "structuring": s_disc.auroc,
        "leakage": float(leak_rows),
        "ece": samples["test"].ece,
        "ablation": ablated.auroc,
    }
    tier, tier_reason = tier_for(decides_automatically=False, informs_person=True, complex_method=False)
    n_entries = con.execute("select count(*) from marts.fct_deposit_entry").fetchone()
    assert n_entries is not None
    card_table = scorecard(labelled, truth, int(n_entries[0]))
    card = ModelCard(
        model_id=MODEL_ID,
        function="f05",
        title="Alert triage for transaction monitoring",
        purpose="Rank the transaction monitoring rules' alerts so an investigator opens the likeliest real typology first",
        tier=tier,
        tier_reason=tier_reason,
        role="sole",
        status="in use",
        prediction_time="When the alert fires; history features use only the account's entries before the alert window opened",
        outcome="The alert overlaps an injected typology episode of the same kind on the same account",
        population="Every alert the four rules fired on Harborline deposit accounts, September 2023 to August 2026",
        backend="generated",
        method="Logistic regression on the alert's facts and the account's prior ninety days, standardised",
        features=list(FEATURES),
        lines={
            "trained": "On alerts that closed before September 2025, labelled by the generator's injected truth.",
            "timed": "History features stop at the alert window's start; a leakage test recomputes 200 sampled alerts from raw entries.",
            "calibrated": "Reliability on the test months is published; the queue uses the score as a rank.",
            "useful": "Beats the base rate and the order the rules alone imply, including within structuring alerts, where the rules cannot rank at all.",
            "fair": "No demographic enters; the features are the alert's facts and the account's own history.",
            "gated": "Every gate in this report, including an ablation without the two features the generator made most different.",
            "served": "Scored in the pipeline; the ranked queue is published with the crime page.",
            "integrated": "Sorts the case queue: an investigator opens alerts in the model's order within each month.",
            "monitored": "Queue capture against investigator dispositions once they exist; monthly score PSI; alert mix by rule.",
            "documented": "This validation report and docs/crime.md.",
            "bounded": "Orders alerts; never closes one, never files anything, and never replaces an investigator's disposition.",
            "validated": "This report, rendered from the manifest before the queue uses the order.",
            "explainable": "Each alert shows the rule's statement in plain words and the features that moved its score most.",
        },
    )
    result = ModelResult(
        card=card,
        samples=samples,
        baselines={
            "Base rate": base,
            "The rules' own order": rule_order,
            "This model without cash history and branches": ablated,
        },
        gates=run_gates(gates, measured),
        reliability=reliability(_y(test), scores["test"]),
        subgroups=None,
        monitoring=[
            (
                "Precision of the queue's first quarter against investigator dispositions",
                "below the rules' own order for two months",
                "Refit on dispositions",
            ),
            ("Score PSI, monthly against development", f"above {cfg.model_risk.psi_breach:g}", "Revalidate"),
            (
                "Alert mix by rule",
                "any rule's share moves by half",
                "Review the rule thresholds before the model",
            ),
        ],
        last_validated=cfg.calendar.as_of.isoformat(),
        extra_values={
            "alerts": (labelled.height, "int"),
            "true_alerts": (int(labelled["true_positive"].sum()), "int"),
            "dev_alerts": (dev.height, "int"),
            "validation_alerts": (val.height, "int"),
            "test_alerts": (test.height, "int"),
            "test_true": (int(_y(test).sum()), "int"),
            "structuring_test": (structuring.height, "int"),
            "structuring_test_true": (int(_y(structuring).sum()), "int"),
            "structuring_auroc": (s_disc.auroc, "float3"),
            "structuring_rule_ap": (s_rule.average_precision, "float3"),
            "ablation_auroc": (ablated.auroc, "float3"),
            "rule_order_auroc": (rule_order.auroc, "float3"),
            "leakage_rows": (leak_rows, "int"),
            "top_features": (", ".join(top_features), "text"),
            "train_period": ("September 2023 to August 2025", "text"),
            "validation_period": ("September 2025 to February 2026", "text"),
            "test_period": ("March to August 2026", "text"),
        },
        extra_tables={
            "coefficients": pl.DataFrame(
                {"feature": list(coef), "coefficient": [float(v) for v in coef.values()]}
            ).sort(pl.col("coefficient").abs(), descending=True),
        },
        extra_formats={"coefficients": ["text", "float2"]},
    )
    challenges = read_challenges(root / "DECISIONS.md")
    m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
    put_result(m, result, challenges)
    m.save(out / "manifest.json")
    write_inventory(models_dir, [inventory_row(result)])
    # The ranked alerts and the rule scorecard, for the crime function and the page.
    frame.with_columns(
        triage=pl.Series(score(frame, FEATURES, fitted)),
    ).drop("open_date").write_parquet(out / "alerts_scored.parquet")
    card_table.write_parquet(out / "rule_scorecard.parquet")
    return result
