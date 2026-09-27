"""Train, evaluate, gate and document pd_scorecard and pd_challenger, on the generated book and on UCI."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl
from ledger_core.config import LedgerConfig
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest
from ledger_core.pit import PointInTimeFrame, recompute_check
from ledger_scorecard.policy_files import load_proxies, load_reason_codes
from ledger_scorecard.scorecard import Scaling

from ledger_models import pd as P
from ledger_models import recovery as R
from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import discrimination, reliability
from ledger_models.gates import Gate, run_gates
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory


@dataclass
class PdOutputs:
    champion: ModelResult
    challenger: ModelResult


def _scaling(cfg: LedgerConfig) -> Scaling:
    s = cfg.scorecard
    return Scaling(s.base_score, s.base_odds, s.points_to_double_odds)


def leakage_check(apps: pl.DataFrame, raw_apps: pl.DataFrame) -> int:
    """Application characteristics are what the bank knew on the application date.

    The recompute takes each sampled application's record from the raw table as
    of strictly before the day after the application (the record is written once,
    at application) and compares every model input.
    """
    history = PointInTimeFrame.build(
        raw_apps.with_columns(known_at=pl.col("application_date").cast(pl.Datetime("us"))),
        "application_id",
        "known_at",
    )
    features = apps.with_columns(
        predict_at=(pl.col("application_date").cast(pl.Datetime("us")) + pl.duration(days=1))
    )

    def recompute(past: pl.DataFrame, row: Mapping[str, Any]) -> dict[str, float]:
        rec = past.row(-1, named=True)
        return {c: float(rec[c]) for c in P.NUMERIC}

    return recompute_check(features, history, "predict_at", recompute, P.NUMERIC)


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> PdOutputs:
    proxies = load_proxies(root / "rules")
    reasons = load_reason_codes(root / "rules", "generated")
    s = cfg.scorecard
    kw = dict(
        scaling=_scaling(cfg),
        cutoff=s.approval_cutoff_score,
        proxies=proxies,
        iv_floor=s.iv_floor,
        correlation_ceiling=s.correlation_ceiling,
        min_bin_share=s.min_bin_share,
        max_fine_bins=s.max_fine_bins,
        seed=cfg.seed,
    )
    data = P.load_generated(con)
    booked = data.booked
    dev = booked.filter(pl.col("split") == "development")
    val = booked.filter(pl.col("split") == "validation")
    fitted = P.fit_all(dev, val, numeric=P.NUMERIC, categorical=P.CATEGORICAL, **kw)  # type: ignore[arg-type]
    preds = P.predict(fitted, booked, P.NUMERIC, P.CATEGORICAL)
    shadow = P.predict(fitted, data.applications, P.NUMERIC, P.CATEGORICAL)
    folder = models_dir / "pd_scorecard"
    P.save_fitted(fitted, folder, "generated")

    # Known structure first: nothing below is trusted until the generator's parameters are recovered.
    truth_dir = root / "data" / "raw" / "truth"
    truth_loans = pl.read_parquet(truth_dir / "truth_loans.parquet")
    stated = json.loads((truth_dir / "truth_parameters.json").read_text())
    dp, bp = stated["default"], stated["betas"]
    hazard = R.recover_default_process(
        R.hazard_frame(con, truth_loans), tuple(dp["loose_vintages"]), cfg.seed
    )
    dev_scores = pl.DataFrame(
        {"loan_id": dev["loan_id"], "pd": preds["champion"][(booked["split"] == "development").to_numpy()]}
    )
    rho = R.rank_order(con, truth_loans, dev_scores)
    betas = R.deposit_betas(
        con, {"checking": bp["checking_floor"], "savings": bp["savings_floor"], "time": 0.50}
    )
    rec24 = R.recovery_share(con)
    recovered = [
        R.Recovered(
            "Latent risk rank order (Spearman; perfect ordering is 1)",
            1.0,
            rho,
            rho,
            rho,
            0.6,
            "Spearman correlation between the generator's latent score and the scorecard's probability",
        ),
        R.Recovered(
            "Latent risk coefficient",
            dp["beta_risk"],
            *hazard["beta_risk"],
            0.15,
            "Discrete time hazard, logistic, month on book effects",
        ),
        R.Recovered(
            "Macro sensitivity per point of unemployment",
            dp["beta_macro"],
            *hazard["beta_macro"],
            0.10,
            "Same hazard fit",
        ),
        R.Recovered(
            "Loose vintage effect", dp["vintage_effect"], *hazard["vintage_effect"], 0.15, "Same hazard fit"
        ),
        R.Recovered(
            "Deposit beta, checking",
            bp["checking"],
            *betas["checking"],
            0.01,
            "OLS of product rate on policy rate, unfloored months",
        ),
        R.Recovered("Deposit beta, savings", bp["savings"], *betas["savings"], 0.03, "Same"),
        R.Recovered("Deposit beta, time", bp["time"], *betas["time"], 0.03, "Same"),
        R.Recovered(
            "Recovery share at 24 months, installment",
            dp["recovery_share_24m"],
            rec24,
            rec24,
            rec24,
            0.05,
            "Cumulative recoveries over charge offs, warehouse recovery mart",
        ),
    ]
    recovery_table = R.table(recovered)
    recovery_table.write_parquet(models_dir / "known_parameters.parquet")
    if not recovery_table["within"].all():
        missed = recovery_table.filter(~pl.col("within"))["parameter"].to_list()
        raise R.RecoveryError(f"known parameters not recovered within tolerance: {missed}")

    # Leakage: every model input recomputed from the application record for 200 sampled rows.
    raw_apps = pl.read_parquet(root / "data" / "staged" / "generated" / "loan_applications.parquet")
    leak_rows = leakage_check(booked, raw_apps)

    y = booked["bad"].to_numpy()
    split = booked["split"].to_numpy()
    test = split == "test"
    dmask = split == "development"
    champ_samples = P.evaluate_samples(booked, preds, "champion")
    chall_samples = P.evaluate_samples(booked, preds, "challenger")
    base = P.base_rate_discrimination(booked)
    logistic = discrimination(y[test], preds["logistic"][test])
    psi_champ = P.stability(preds["score"][dmask], preds["score"][test])
    psi_chall = P.stability(preds["challenger"][dmask], preds["challenger"][test])
    approved = preds["score"] >= s.approval_cutoff_score
    test_frame = booked.filter(pl.col("split") == "test")
    audit_champ = P.audit_by_age(test_frame, preds["champion"][test], approved[test])
    chall_cut = float(np.quantile(preds["challenger"][dmask], 1 - float(approved[dmask].mean())))
    audit_chall = P.audit_by_age(test_frame, preds["challenger"][test], preds["challenger"][test] < chall_cut)
    agreement = P.rank_agreement(shadow["champion"], shadow["challenger"])

    # Reason codes for every declined application in the test months.
    apps = data.applications.with_columns(
        score=pl.Series(shadow["score"]),
        pd_champion=pl.Series(shadow["champion"]),
        pd_challenger=pl.Series(shadow["challenger"]),
    )
    declined_test = apps.filter(
        (pl.col("score") < s.approval_cutoff_score)
        & (pl.col("month") >= "2025-03")
        & (pl.col("month") <= "2025-08")
    )
    first_reason = [
        r[0] if r else None
        for r in P.reasons_for(fitted.card, declined_test, reasons, proxies, s.reason_codes_returned)
    ]
    reason_counts = (
        pl.DataFrame({"characteristic": first_reason})
        .drop_nulls()
        .group_by("characteristic")
        .len()
        .sort("len", descending=True)
        .with_columns(
            share=pl.col("len") / pl.col("len").sum(), reason=pl.col("characteristic").replace_strict(reasons)
        )
    )
    scored = apps.select(
        "application_id",
        "month",
        "decision",
        "booked",
        "score",
        "pd_champion",
        "pd_challenger",
        pl.col("default_12m"),
        pl.col("loan_id"),
    ).with_columns(
        decision_at_cutoff=pl.when(pl.col("score") >= s.approval_cutoff_score)
        .then(pl.lit("approve"))
        .otherwise(pl.lit("decline"))
    )
    scored.write_parquet(folder / "applications_scored.parquet")
    fitted.card.table().write_parquet(folder / "scorecard_generated.parquet")

    challenges = read_challenges(root / "DECISIONS.md")
    today = cfg.calendar.as_of.isoformat()
    tier, tier_reason = tier_for(decides_automatically=True, informs_person=True, complex_method=False)
    gates_champ = [
        Gate("rank_order", "Recovers the generator's latent risk ordering (Spearman)", "at_least", 0.40),
        Gate("auroc", "Test AUROC at or above the floor", "at_least", 0.62),
        Gate("vs_logistic", "Test AUROC no more than 0.02 below the logistic benchmark", "at_least", -0.02),
        Gate("psi", "Score stability, development to test (PSI)", "at_most", cfg.model_risk.psi_breach),
        Gate("fair_air", "Lowest adverse impact ratio across age bands", "at_least", 0.80),
        Gate("leakage", "Point in time recompute of sampled rows", "at_least", 200),
        Gate("ece", "Expected calibration error on test", "at_most", 0.02, critical=False),
    ]
    measured_champ = {
        "rank_order": rho,
        "auroc": champ_samples["test"].auroc,
        "vs_logistic": champ_samples["test"].auroc - logistic.auroc,
        "psi": psi_champ,
        "fair_air": _min(audit_champ["adverse_impact_ratio"]),
        "leakage": float(leak_rows),
        "ece": champ_samples["test"].ece,
    }
    champ_card = ModelCard(
        model_id="pd_scorecard",
        function="f02",
        title="Probability of default scorecard (champion)",
        purpose="Rank and price installment loan applications by twelve month default risk and state the reasons for a decline",
        tier=tier,
        tier_reason=tier_reason,
        role="champion",
        status="in use",
        prediction_time="The application date, before any loan exists",
        outcome=f"{cfg.censoring.default_dpd} days past due or charge off within {cfg.censoring.default_window_months} months of origination",
        population="booked installment loans with an observed outcome",
        backend="generated",
        method="Weight of evidence scorecard: coarse classed monotone bins, logistic regression on WoE, points scaled",
        features=[c.name for c in fitted.card.characteristics],
        lines={
            "trained": "On loans originated in the first twelve months of the window, with outcomes observed under the censoring calendar.",
            "timed": "Scores the application as submitted; a leakage test recomputes 200 sampled rows from the application record.",
            "calibrated": "Points convert back to the logistic probability exactly; calibration on later vintages is reported, not assumed.",
            "useful": "Benchmarked on the out of time test sample against the base rate, a logistic model on raw characteristics and the challenger.",
            "fair": "Approval rates, AUROC and calibration by applicant age band; age is never an input.",
            "gated": "Promoted only after every gate in its validation report passed or was accepted with a stated condition.",
            "served": "POST /v1/scorecard/score in the API; in the browser from the published scorecard table on /studio.",
            "integrated": "Sets the approve or decline decision at the stated cutoff and supplies expected loss in function 2.",
            "monitored": "Score PSI and characteristic stability monthly; rolling AUROC and calibration as twelve month outcomes arrive.",
            "documented": "This validation report, the scorecard table, and docs/models.md.",
            "bounded": "Scores installment loan applications only; it has never seen a card or mortgage application.",
            "validated": "This report, rendered from the manifest before the model is used anywhere.",
            "explainable": "Every decline returns up to four adverse action reasons, the largest point shortfalls, in plain words.",
        },
    )
    monitoring = [
        (
            "Score PSI, monthly applications against development",
            f"above {cfg.model_risk.psi_warning:g} warns, above {cfg.model_risk.psi_breach:g} breaches",
            "Investigate the shift; revalidate on breach",
        ),
        (
            "Characteristic stability index, each characteristic",
            f"above {cfg.model_risk.psi_breach:g}",
            "Review the characteristic's bins",
        ),
        ("Rolling test AUROC as outcomes mature", "falls 0.03 below the validation figure", "Redevelop"),
        (
            "Observed over predicted default by vintage",
            "outside 0.8 to 1.25 for two vintages",
            "Recalibrate the intercept or apply an overlay",
        ),
    ]
    champion = ModelResult(
        card=champ_card,
        samples=champ_samples,
        baselines={
            "Base rate": base,
            "Logistic on raw characteristics": logistic,
            "Challenger (GBM)": chall_samples["test"],
        },
        gates=run_gates(gates_champ, measured_champ),
        reliability=reliability(y[test], preds["champion"][test]),
        subgroups=audit_champ,
        monitoring=monitoring,
        last_validated=today,
        extra_values={
            "psi_dev_test": (psi_champ, "float4"),
            "leakage_rows": (leak_rows, "int"),
            "characteristics": (len(fitted.card.characteristics), "int"),
            "candidates": (len(P.FEATURES), "int"),
            "cutoff": (s.approval_cutoff_score, "int"),
            "approval_rate_test": (float(approved[test].mean()), "pct1"),
            "rank_agreement": (agreement, "float3"),
            "rank_order": (rho, "float3"),
            "declined_test_months": (declined_test.height, "int"),
            "mean_pd_test": (float(preds["champion"][test].mean()), "pct2"),
            "observed_test": (float(y[test].mean()), "pct2"),
            "mean_pd_validation": (float(preds["champion"][split == "validation"].mean()), "pct2"),
            "observed_validation": (float(y[split == "validation"].mean()), "pct2"),
        },
        extra_tables={
            "scorecard": fitted.card.table().select(
                "characteristic", "bin", "share", "bad_rate", "woe", "points"
            ),
            "iv": pl.DataFrame(
                {
                    "characteristic": list(fitted.card.iv),
                    "iv": list(fitted.card.iv.values()),
                    "kept": [
                        "kept"
                        if c in [x.name for x in fitted.card.characteristics]
                        else fitted.card.dropped.get(c, "")
                        for c in fitted.card.iv
                    ],
                }
            ).sort("iv", descending=True),
            "reasons": reason_counts.select("reason", "len", "share").rename({"len": "declines"}),
            "known_parameters": recovery_table.select(
                "parameter", "stated", "estimate", "interval_low", "interval_high", "tolerance", "within"
            ).with_columns(pl.col("within").cast(pl.Utf8)),
        },
        extra_formats={
            "scorecard": ["text", "text", "pct1", "pct2", "float3", "float1"],
            "iv": ["text", "float3", "text"],
            "reasons": ["text", "int", "pct1"],
            "known_parameters": ["text", "float3", "float3", "float3", "float3", "float3", "text"],
        },
    )

    ctier, ctier_reason = tier_for(decides_automatically=False, informs_person=True, complex_method=True)
    gates_chall = [
        Gate("improvement", "Test AUROC at least 0.01 above the champion", "at_least", 0.01),
        Gate("psi", "Score stability, development to test (PSI)", "at_most", cfg.model_risk.psi_breach),
        Gate(
            "fair_air",
            "Lowest adverse impact ratio across age bands at the champion's approval rate",
            "at_least",
            0.80,
        ),
        Gate("ece", "Expected calibration error on test", "at_most", 0.02, critical=False),
        Gate(
            "agreement",
            "Rank agreement with the champion on every application (Spearman)",
            "at_least",
            0.70,
            critical=False,
        ),
    ]
    measured_chall = {
        "improvement": chall_samples["test"].auroc - champ_samples["test"].auroc,
        "psi": psi_chall,
        "fair_air": _min(audit_chall["adverse_impact_ratio"]),
        "ece": chall_samples["test"].ece,
        "agreement": agreement,
    }
    chall_card = ModelCard(
        model_id="pd_challenger",
        function="f02",
        title="Probability of default challenger (monotone GBM)",
        purpose="Test whether a gradient boosted model beats the scorecard enough to justify its opacity",
        tier=ctier,
        tier_reason=ctier_reason,
        role="challenger",
        status="validated",
        prediction_time="The application date",
        outcome=champ_card.outcome,
        population=champ_card.population,
        backend="generated",
        method="LightGBM with monotone constraints matching the scorecard's weight of evidence directions, early stopped on validation",
        features=list(P.FEATURES),
        lines={
            "trained": "Same development sample as the champion, early stopped on the validation months.",
            "timed": "Same application record as the champion, under the same leakage test.",
            "calibrated": "Reported on the out of time test sample beside the champion's calibration.",
            "useful": "Judged only against the champion, on the same test sample, by a stated materiality margin.",
            "fair": "The same age band audit, at the threshold that approves the champion's share of applicants.",
            "gated": "Promotion requires every gate in this report; it has not been promoted.",
            "served": "Shadow scored in batch on every application, including declines; not served for decisions.",
            "integrated": "Its scores sit beside the champion's in the applications table for the comparison and nothing else.",
            "monitored": "Rank agreement with the champion and its own stability, monthly, while it remains in shadow.",
            "documented": "This validation report and docs/models.md.",
            "bounded": "Not used for any decision while in shadow; cannot produce Regulation B reasons without a separate explanation method.",
            "validated": "This report, rendered from the manifest.",
            "explainable": "Monotone constraints keep each characteristic's effect in the scorecard's direction; feature contributions are published, but adverse action reasons still come from the champion.",
        },
    )
    challenger = ModelResult(
        card=chall_card,
        samples=chall_samples,
        baselines={
            "Champion scorecard": champ_samples["test"],
            "Logistic on raw characteristics": logistic,
            "Base rate": base,
        },
        gates=run_gates(gates_chall, measured_chall),
        reliability=reliability(y[test], preds["challenger"][test]),
        subgroups=audit_chall,
        monitoring=[
            ("Rank agreement with the champion", "below 0.7", "Investigate before any promotion case")
        ],
        last_validated=today,
        extra_values={
            "psi_dev_test": (psi_chall, "float4"),
            "improvement": (measured_chall["improvement"], "float3"),
            "trees": (fitted.challenger.num_trees() if fitted.challenger else 0, "int"),
            "rank_agreement": (agreement, "float3"),
        },
    )

    # The same machinery on 30,000 real accounts.
    uci = P.load_uci(root / "data" / "staged" / "real" / "uci_default.parquet", cfg.seed)
    u_dev = uci.filter(pl.col("split") == "development")
    u_val = uci.filter(pl.col("split") == "validation")
    u_fit = P.fit_all(u_dev, u_val, numeric=P.UCI_NUMERIC, categorical=[], **kw)  # type: ignore[arg-type]
    P.save_fitted(u_fit, folder, "uci")
    u_pred = P.predict(u_fit, uci, P.UCI_NUMERIC, [])
    u_champ = P.evaluate_samples(uci, u_pred, "champion")
    u_chall = P.evaluate_samples(uci, u_pred, "challenger")
    u_log = P.evaluate_samples(uci, u_pred, "logistic")
    u_table = u_fit.card.table().select("characteristic", "bin", "share", "bad_rate", "woe", "points")
    u_table.write_parquet(folder / "scorecard_uci.parquet")
    champion.extra_tables["uci_scorecard"] = u_table
    champion.extra_formats["uci_scorecard"] = ["text", "text", "pct1", "pct2", "float3", "float1"]
    champion.extra_tables["uci_iv"] = pl.DataFrame(
        {
            "characteristic": list(u_fit.card.iv),
            "iv": list(u_fit.card.iv.values()),
            "kept": [
                "kept" if c in [x.name for x in u_fit.card.characteristics] else u_fit.card.dropped.get(c, "")
                for c in u_fit.card.iv
            ],
        }
    ).sort("iv", descending=True)
    champion.extra_formats["uci_iv"] = ["text", "float3", "text"]
    rows = [
        ("Loans or accounts with an outcome", float(booked.height), float(uci.height), "int"),
        ("Default rate", float(y.mean()), float(uci["bad"].mean()), "pct1"),  # type: ignore[arg-type]
        (
            "Characteristics kept",
            float(len(fitted.card.characteristics)),
            float(len(u_fit.card.characteristics)),
            "int",
        ),
        ("Scorecard AUROC, test", champ_samples["test"].auroc, u_champ["test"].auroc, "float3"),
        ("Scorecard Gini, test", champ_samples["test"].gini, u_champ["test"].gini, "float3"),
        ("Challenger AUROC, test", chall_samples["test"].auroc, u_chall["test"].auroc, "float3"),
        ("Logistic AUROC, test", logistic.auroc, u_log["test"].auroc, "float3"),
        ("Scorecard calibration error, test", champ_samples["test"].ece, u_champ["test"].ece, "float4"),
    ]
    champion.extra_tables["side_by_side"] = pl.DataFrame(
        {
            "measure": [r[0] for r in rows],
            "generated": [format_value(r[1], r[3]) for r in rows],
            "uci": [format_value(r[2], r[3]) for r in rows],
        }
    )
    champion.extra_formats["side_by_side"] = ["text", "text", "text"]
    champion.extra_values["uci_accounts"] = (uci.height, "int")
    for name, d in (
        ("uci_auroc", u_champ["test"].auroc),
        ("uci_gini", u_champ["test"].gini),
        ("uci_challenger_auroc", u_chall["test"].auroc),
        ("uci_logistic_auroc", u_log["test"].auroc),
    ):
        champion.extra_values[name] = (d, "float3")

    for result in (champion, challenger):
        m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
        put_result(m, result, challenges)
        (models_dir / result.card.model_id).mkdir(parents=True, exist_ok=True)
        m.save(models_dir / result.card.model_id / "manifest.json")
    write_inventory(models_dir, [inventory_row(champion), inventory_row(challenger)])
    return PdOutputs(champion, challenger)


def _min(series: pl.Series) -> float:
    value = series.min()
    return float(value) if isinstance(value, int | float) else float("nan")
