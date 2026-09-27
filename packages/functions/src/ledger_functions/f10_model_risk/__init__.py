"""Function 10: model risk management.

Question: which models does the bank use, is each validated, and is each still doing
what it was validated to do? The inventory with tiers, roles, status and conclusions;
monitoring by population and characteristic stability, and discrimination as labels
arrive; and the effective challenge log. Each model's validation report is rendered
separately by the claim gate.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Scalar
from ledger_models.report import read_challenges
from ledger_scorecard.scorecard import Scorecard, psi
from sklearn.metrics import roc_auc_score

from ledger_functions.base import Context, FunctionSpec

MODEL_ORDER = (
    "pd_scorecard",
    "pd_challenger",
    "fraud_card",
    "fraud_account",
    "aml_triage",
    "attrition",
    "relief",
    "cure",
)


def csi(expected_idx: np.ndarray, actual_idx: np.ndarray, bins: int) -> float:
    e = np.clip(np.bincount(expected_idx, minlength=bins) / expected_idx.size, 1e-6, None)
    a = np.clip(np.bincount(actual_idx, minlength=bins) / actual_idx.size, 1e-6, None)
    return float(((a - e) * np.log(a / e)).sum())


def run(ctx: Context) -> None:
    m = ctx.manifest
    prov: dict[str, Any] = {
        "backend": "mixed",
        "population": "the model inventory",
        "source": "results/models/registry.json",
    }
    registry = json.loads((ctx.paths.models_dir / "registry.json").read_text())
    rows: list[list[Scalar]] = []
    for model_id in MODEL_ORDER:
        entry = registry.get(model_id)
        if entry is None:
            continue
        rows.append(
            [
                model_id,
                entry["title"],
                entry["function"],
                str(entry["tier"]),
                entry["role"],
                entry["status"],
                entry["last_validated"],
                entry["conclusion"],
                entry["auroc_test"],
            ]
        )
    m.put_table(
        "f10.inventory",
        [
            "Model",
            "Title",
            "Function",
            "Tier",
            "Role",
            "Status",
            "Last validated",
            "Conclusion",
            "Test AUROC",
        ],
        ["text"] * 8 + ["float3"],
        rows,
        **prov,
    )
    ctx.save(
        "inventory",
        pl.DataFrame(
            rows,
            schema=[
                "model",
                "title",
                "function",
                "tier",
                "role",
                "status",
                "last_validated",
                "conclusion",
                "auroc_test",
            ],
            orient="row",
        ),
    )
    m.put("f10.models", len(rows), "int", **prov)
    m.put("f10.approved", sum(r[7] == "approved" for r in rows), "int", **prov)
    m.put("f10.with_conditions", sum(r[7] == "approved with conditions" for r in rows), "int", **prov)
    m.put("f10.not_approved", sum(r[7] == "not approved" for r in rows), "int", **prov)

    # pd_scorecard: score PSI by application quarter against development, and CSI per characteristic.
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "every installment application, approved or declined",
        "source": "pd_scorecard",
    }
    card = Scorecard.load(ctx.paths.models_dir / "pd_scorecard" / "scorecard_generated.json")
    apps = ctx.sql("select * from staging.stg_loan_applications")
    apps = apps.with_columns(
        quarter=pl.col("application_date").dt.year().cast(pl.Utf8)
        + "Q"
        + pl.col("application_date").dt.quarter().cast(pl.Utf8)
    )
    scores = card.score(apps)
    dev_mask = (apps["application_date"] < date(2024, 9, 1)).to_numpy()
    psi_rows: list[list[Scalar]] = []
    for quarter in sorted(apps["quarter"].unique().to_list()):
        mask = (apps["quarter"] == quarter).to_numpy()
        psi_rows.append([quarter, int(mask.sum()), psi(scores[dev_mask], scores[mask])])
    psi_frame = pl.DataFrame(psi_rows, schema=["quarter", "applications", "psi"], orient="row")
    ctx.save("pd_psi_by_quarter", psi_frame)
    worst = psi_frame.sort("psi").row(-1, named=True)
    m.put("f10.pd_psi_worst", worst["psi"], "float3", **gen)
    m.put("f10.pd_psi_worst_quarter", worst["quarter"], "text", **gen)
    recent_mask = (apps["application_date"] >= date(2026, 3, 1)).to_numpy()
    csi_rows: list[list[Scalar]] = []
    for c in card.characteristics:
        idx = np.array([c.table.index_of(v) for v in apps[c.name].to_list()], dtype=np.int64)
        csi_rows.append([c.name, csi(idx[dev_mask], idx[recent_mask], len(c.table.bins))])
    csi_frame = pl.DataFrame(csi_rows, schema=["characteristic", "csi"], orient="row").sort(
        "csi", descending=True
    )
    ctx.save("pd_csi", csi_frame)
    m.put_table(
        "f10.pd_csi",
        ["Characteristic", "Stability index, last six months against development"],
        ["text", "float3"],
        csi_frame.rows(),
        **gen,
    )
    breach = ctx.config.model_risk.psi_breach
    warn = ctx.config.model_risk.psi_warning
    m.put_figure(
        "f10.fig_psi",
        "Score stability by application quarter, against the development quarters",
        f"The worst quarter's population stability index is {format_value(worst['psi'], 'float3')} "
        f"({worst['quarter']}), against a warning line at {format_value(warn, 'float2')} and a breach at "
        f"{format_value(breach, 'float2')}. Stability says the applicants look alike; it says nothing about "
        f"whether they default alike, which is why calibration is monitored separately as outcomes mature.",
        data="f10/pd_psi_by_quarter.parquet",
        **gen,
    )

    # fraud_card: weekly score PSI against validation, and AUROC over what had been labelled by each week's end.
    rep: dict[str, Any] = {
        "backend": "replayed",
        "population": "fraud_card scored stream, April to August 2026",
        "source": "fraud_card",
    }
    stream = pl.read_parquet(ctx.paths.models_dir / "fraud_card" / "scored_stream.parquet")
    cb = ctx.config.censoring.chargeback_window_days
    val_scores = stream.filter(pl.col("split") == "validation")["score"].to_numpy()
    test = stream.filter(pl.col("split") == "test").with_columns(
        week=pl.col("transaction_time").dt.truncate("1w")
    )
    weekly = []
    for week, part in test.group_by("week", maintain_order=True):
        week_start = week[0]
        week_end = week_start + timedelta(days=7)
        seen = stream.filter(pl.col("transaction_time") < week_end)
        labelled = seen.filter(pl.col("transaction_time") <= week_end - timedelta(days=cb))
        labelled_test = labelled.filter(pl.col("split") == "test")
        auc = None
        if labelled_test.height > 100 and 0 < labelled_test["is_fraud"].sum() < labelled_test.height:
            auc = float(
                roc_auc_score(labelled_test["is_fraud"].to_numpy(), labelled_test["score"].to_numpy())
            )
        weekly.append(
            [
                week_start.date().isoformat(),
                part.height,
                psi(val_scores, part["score"].to_numpy()),
                labelled_test.height,
                auc,
            ]
        )
    weekly_frame = pl.DataFrame(
        weekly, schema=["week", "transactions", "psi", "labelled_test", "auroc_labelled"], orient="row"
    ).sort("week")
    ctx.save("fraud_weekly", weekly_frame)
    first_auc = weekly_frame.filter(pl.col("auroc_labelled").is_not_null())
    m.put(
        "f10.fraud_weeks_without_labels",
        weekly_frame.filter(pl.col("auroc_labelled").is_null()).height,
        "int",
        **rep,
    )
    m.put(
        "f10.fraud_first_labelled_week", first_auc["week"][0] if first_auc.height else "none", "text", **rep
    )
    m.put("f10.fraud_psi_max", float(weekly_frame["psi"].max()), "float3", **rep)  # type: ignore[arg-type]
    m.put_figure(
        "f10.fig_fraud_monitoring",
        "The fraud model's monitoring, week by week",
        f"Score stability is measurable the day a transaction is scored; discrimination is not. For the first "
        f"{weekly_frame.filter(pl.col('auroc_labelled').is_null()).height} weeks of the test months no test "
        f"transaction had cleared the {cb} day chargeback window, so the model's AUROC on the new months could not be "
        f"computed at all. That gap is the monitoring lag, and the plan says so rather than filling it.",
        data="f10/fraud_weekly.parquet",
        **rep,
    )

    challenges = read_challenges(ctx.paths.root / "DECISIONS.md")
    m.put_table(
        "f10.challenges",
        ["Date", "Models", "Challenge", "What changed"],
        ["text"] * 4,
        [[c.date, ", ".join(c.models), c.raised, c.changed] for c in challenges],
        backend="static",
        population="DECISIONS.md",
        source="effective challenge log",
    )
    m.put(
        "f10.challenge_count",
        len(challenges),
        "int",
        backend="static",
        population="DECISIONS.md",
        source="effective challenge log",
    )


SPEC = FunctionSpec(
    code="f10",
    slug="models",
    title="Model risk management",
    question="Which models does the bank use, is each validated, and is each still doing what it was validated to do?",
    run=run,
)
