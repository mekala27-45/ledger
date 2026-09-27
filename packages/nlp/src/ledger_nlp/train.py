"""relief: will a complaint end in monetary relief?

From the narrative the consumer wrote and the metadata filed with it, the chance the
company's response is "closed with monetary relief". Real public data about real
companies, as the Bureau publishes it. TF-IDF and a logistic regression is the path that
needs nothing downloaded; a transformer would need model weights this build cannot reach,
and the report says so.

What it is for in a bank: routing a complaint to the team that can fix it, and finding
the root causes behind complaints that end in refunds. What it must never be used for:
deciding whether a consumer gets relief, or ranking consumers.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import yaml
from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest
from ledger_models.contract import ModelCard, tier_for
from ledger_models.evaluate import confusion_at, discrimination, reliability, subgroup_table
from ledger_models.gates import Gate, conclusion, run_gates
from ledger_models.report import ModelResult, inventory_row, put_result, read_challenges, write_inventory
from ledger_scorecard.policy_files import load_proxies
from ledger_scorecard.scorecard import check_proxies
from scipy import sparse
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

MODEL_ID = "relief"
TRAIN = ("2024-09", "2025-12")
VALIDATION = ("2026-01", "2026-03")
TEST = ("2026-04", "2026-07")
METADATA = ("product", "sub_product", "issue", "company")
# Written when the consumer files. Everything else in a complaint record (the company's
# response, its public statement, whether it was timely) is written after, by the company.
SUBMISSION_FIELDS = frozenset({"consumer_complaint_narrative", *METADATA, "date_received", "submitted_via"})
FEATURES = ("narrative_tfidf", *METADATA)
FLAG_SHARE = 0.05
C_GRID = (0.05, 0.1, 0.25, 0.5, 1.0)


class TimingError(ValueError):
    pass


def check_timing(fields: list[str]) -> None:
    late = sorted(set(fields) - SUBMISSION_FIELDS)
    if late:
        raise TimingError(f"fields written after the complaint was filed offered as features: {late}")


def text_terms(rules: Path) -> list[str]:
    data = yaml.safe_load((rules / "proxies.yaml").read_text(encoding="utf-8"))
    return [str(t).lower() for t in data.get("text_terms", [])]


def split(frame: pl.DataFrame, window: tuple[str, str]) -> pl.DataFrame:
    return frame.filter(pl.col("month").is_between(pl.lit(window[0]), pl.lit(window[1])))


def build(train: pl.DataFrame, rules: Path) -> tuple[TfidfVectorizer, OneHotEncoder]:
    banned = set(text_terms(rules))
    vectorizer = TfidfVectorizer(
        max_features=30_000,
        min_df=5,
        max_df=0.5,
        ngram_range=(1, 2),
        stop_words=sorted(ENGLISH_STOP_WORDS | {"xxxx", "xx", "xxx"} | banned),
        token_pattern=r"(?u)\b[a-z][a-z]{2,}\b",
        sublinear_tf=True,
    )
    vectorizer.fit(train["narrative"].to_list())
    kept = [t for t in vectorizer.get_feature_names_out() if not (set(t.split()) & banned)]
    vectorizer.vocabulary_ = {t: i for i, t in enumerate(kept)}
    encoder = OneHotEncoder(handle_unknown="ignore", min_frequency=20)
    encoder.fit(train.select(METADATA).to_pandas())
    return vectorizer, encoder


def design(
    frame: pl.DataFrame, vectorizer: TfidfVectorizer, encoder: OneHotEncoder, text: bool = True
) -> sparse.csr_matrix:
    meta = encoder.transform(frame.select(METADATA).to_pandas())
    if not text:
        return sparse.csr_matrix(meta)
    return sparse.hstack([vectorizer.transform(frame["narrative"].to_list()), meta]).tocsr()


def _choose(
    x: sparse.csr_matrix, y: np.ndarray, x_val: sparse.csr_matrix, y_val: np.ndarray
) -> tuple[LogisticRegression, float, float]:
    from sklearn.metrics import roc_auc_score

    best: tuple[LogisticRegression, float, float] | None = None
    for c in C_GRID:
        fitted = LogisticRegression(C=c, max_iter=3000, solver="liblinear").fit(x, y)
        auc = float(roc_auc_score(y_val, fitted.predict_proba(x_val)[:, 1]))
        if best is None or auc > best[2]:
            best = (fitted, c, auc)
    assert best is not None
    return best


def run(con: duckdb.DuckDBPyConnection, cfg: LedgerConfig, root: Path, models_dir: Path) -> ModelResult:
    out = models_dir / MODEL_ID
    out.mkdir(parents=True, exist_ok=True)
    check_timing(["consumer_complaint_narrative", *METADATA])
    check_proxies(list(FEATURES), load_proxies(root / "rules"))
    raw = pl.read_parquet(root / "data" / "staged" / "real" / "cfpb_narratives.parquet")
    frame = raw.filter(pl.col("company_response_to_consumer") != "In progress").select(
        "complaint_id",
        "month",
        "product",
        pl.col("sub_product").fill_null(""),
        "issue",
        "company",
        pl.col("tags").fill_null(""),
        pl.col("consumer_complaint_narrative").alias("narrative"),
        pl.col("monetary_relief").cast(pl.Int8),
    )
    train, val, test = split(frame, TRAIN), split(frame, VALIDATION), split(frame, TEST)
    y = {
        n: f["monetary_relief"].to_numpy().astype(float)
        for n, f in (("train", train), ("val", val), ("test", test))
    }
    vectorizer, encoder = build(train, root / "rules")
    x_train, x_val = design(train, vectorizer, encoder), design(val, vectorizer, encoder)
    m_train, m_val = (
        design(train, vectorizer, encoder, text=False),
        design(val, vectorizer, encoder, text=False),
    )
    # The regularisation strength of each model is chosen on the validation months.
    model, c_text, val_text = _choose(x_train, y["train"], x_val, y["val"])
    meta_model, c_meta, val_meta = _choose(m_train, y["train"], m_val, y["val"])

    def score(f: pl.DataFrame) -> np.ndarray:
        return np.asarray(model.predict_proba(design(f, vectorizer, encoder))[:, 1])

    p = {"train": score(train), "val": score(val), "test": score(test)}
    samples = {
        "development": discrimination(y["train"], p["train"]),
        "validation": discrimination(y["val"], p["val"]),
        "test": discrimination(y["test"], p["test"]),
    }
    meta_d = discrimination(
        y["test"], meta_model.predict_proba(design(test, vectorizer, encoder, text=False))[:, 1]
    )
    base = discrimination(y["test"], np.full(y["test"].size, float(y["train"].mean())))
    # The operating point: a review team that can read one complaint in twenty, set on validation.
    threshold = float(np.quantile(p["val"], 1 - FLAG_SHARE))
    at_op = confusion_at(y["test"], p["test"], threshold)
    groups = np.where(test["tags"].str.contains("Older American").to_numpy(), "Older American", "Other")
    groups = np.where(
        test["tags"].str.contains("Servicemember").to_numpy(), np.char.add(groups, ", servicemember"), groups
    )
    audit = subgroup_table(y["test"], p["test"], np.asarray(groups), threshold=threshold)
    flag = [r for r in audit["flag_rate"].to_list() if r is not None]

    gates = [
        Gate(
            "vs_metadata",
            "Test AUROC above the metadata only model: the narrative has to add something",
            "at_least",
            0.02,
        ),
        Gate("precision", "Test precision at the operating point over the base rate (lift)", "at_least", 2.0),
        Gate("auroc", "Test AUROC at or above the floor", "at_least", 0.70),
        Gate(
            "flag_ratio",
            "Lowest over highest flag rate across the Bureau's tag groups",
            "at_least",
            0.5,
            critical=False,
        ),
        Gate("ece", "Expected calibration error on test", "at_most", 0.02, critical=False),
    ]
    lift = at_op["precision"] / float(y["test"].mean())
    measured = {
        "vs_metadata": samples["test"].auroc - meta_d.auroc,
        "precision": lift,
        "auroc": samples["test"].auroc,
        "flag_ratio": min(flag) / max(flag) if flag and max(flag) > 0 else None,
        "ece": samples["test"].ece,
    }

    gate_results = run_gates(gates, measured)
    verdict, _ = conclusion(gate_results)
    approved = verdict != "not approved"
    # The conduct risk view: issues ranked by the relief expected on recent complaints, from the
    # text model if it earned its place and from the form's metadata alone if it did not.
    expected = (
        p["test"]
        if approved
        else meta_model.predict_proba(design(test, vectorizer, encoder, text=False))[:, 1]
    )
    recent = test.with_columns(expected=pl.Series(expected))
    issues = (
        recent.group_by("product", "issue")
        .agg(
            pl.len().alias("complaints"),
            pl.col("expected").sum().alias("expected_relief"),
            pl.col("monetary_relief").sum().alias("actual_relief"),
        )
        .filter(pl.col("complaints") >= 30)
        .with_columns(rate=pl.col("expected_relief") / pl.col("complaints"))
        .sort("expected_relief", descending=True)
    )
    issues.write_parquet(out / "issues.parquet")

    vocab = np.array(vectorizer.get_feature_names_out())
    coef = model.coef_[0][: len(vocab)]
    order = np.argsort(-coef)
    terms = pl.DataFrame(
        {
            "raises_relief": vocab[order[:15]].tolist(),
            "weight_up": [float(c) for c in coef[order[:15]]],
            "lowers_relief": vocab[order[::-1][:15]].tolist(),
            "weight_down": [float(c) for c in coef[order[::-1][:15]]],
        }
    )
    tier, tier_reason = tier_for(decides_automatically=False, informs_person=True, complex_method=False)
    card = ModelCard(
        model_id=MODEL_ID,
        function="f07",
        title="Monetary relief on consumer complaints",
        purpose="Route complaints likely to end in a refund to the team that can fix the cause, and rank issues by the relief they are likely to cost",
        tier=tier,
        tier_reason=tier_reason,
        role="sole",
        status="in use" if approved else "development",
        prediction_time="When the complaint is filed; only the narrative and what the consumer chose on the form",
        outcome="The company closed the complaint with monetary relief",
        population="Complaints with narratives in the Bureau's public database, a sample from September 2024 to August 2026",
        backend="real:cfpb",
        method="TF-IDF of the narrative, one and two word terms, with product, sub product, issue and company one hot; logistic regression",
        features=list(FEATURES),
        lines={
            "trained": "On complaints received September 2024 to December 2025; validation January to March 2026 sets the operating point.",
            "timed": "Only fields the consumer writes when filing; a check refuses any field the company writes afterwards, such as its response.",
            "calibrated": "Reliability on the test months is published; the base rate rose over the window, which the report states.",
            "useful": "Beats a model on the form's metadata alone, so the narrative adds something, and lifts precision well above the base rate at the operating point.",
            "fair": "Words naming a protected basis are removed from the vocabulary; flag rates by the Bureau's older American and servicemember tags are audited.",
            "gated": "Every gate in this report.",
            "served": "Scored in the pipeline over the loaded window; not served by the API.",
            "integrated": (
                "Ranks open issues by expected relief in the conduct risk view on the complaints page."
                if approved
                else "Not integrated. Until the narrative earns its place, the conduct risk view ranks issues with the model on the form's metadata alone."
            ),
            "monitored": "Monthly: precision at the operating point against closed complaints, the base rate, and flag rates by tag.",
            "documented": "This validation report and the complaints page.",
            "bounded": "Routes and ranks. Never decides whether a consumer gets relief, and never ranks consumers.",
            "validated": "This report, rendered from the manifest before the ranking is used.",
            "explainable": "The terms that raise and lower the score most are published; a routed complaint shows its product and issue.",
        },
    )
    result = ModelResult(
        card=card,
        samples=samples,
        baselines={"Base rate": base, "The form's metadata alone": meta_d},
        gates=gate_results,
        reliability=reliability(y["test"], p["test"]),
        subgroups=audit,
        monitoring=[
            (
                "Precision at the operating point against closed complaints",
                "below twice the base rate for a quarter",
                "Refit",
            ),
            ("The monthly base rate of monetary relief", "moves by half", "Reset the operating point"),
            ("Flag rate by the Bureau's tags", "any group below half the highest", "Review the vocabulary"),
        ],
        last_validated=cfg.calendar.as_of.isoformat(),
        extra_values={
            "train_period": ("September 2024 to December 2025", "text"),
            "validation_period": ("January to March 2026", "text"),
            "test_period": ("April to July 2026", "text"),
            "complaints": (frame.height, "int"),
            "test_rows": (test.height, "int"),
            "test_relief": (int(y["test"].sum()), "int"),
            "train_rate": (float(y["train"].mean()), "pct1"),
            "test_rate": (float(y["test"].mean()), "pct1"),
            "flag_share": (FLAG_SHARE, "pct0"),
            "precision_op": (at_op["precision"], "pct1"),
            "recall_op": (at_op["recall"], "pct1"),
            "flagged_op": (at_op["flagged"], "int"),
            "lift_op": (lift, "float1"),
            "metadata_auroc": (meta_d.auroc, "float3"),
            "c_text": (c_text, "float2"),
            "c_metadata": (c_meta, "float2"),
            "val_text": (val_text, "float3"),
            "val_metadata": (val_meta, "float3"),
            "vocabulary": (len(vocab), "int"),
            "banned_terms": (len(text_terms(root / "rules")), "int"),
            "top_issue": (f"{issues['issue'][0]} ({issues['product'][0]})", "text"),
            "ranking_source": (
                "this model" if approved else "the model on the form's metadata alone",
                "text",
            ),
            "narrative_gain": (samples["test"].auroc - meta_d.auroc, "float3"),
        },
        extra_tables={"terms": terms},
        extra_formats={"terms": ["text", "float2", "text", "float2"]},
    )
    challenges = read_challenges(root / "DECISIONS.md")
    m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)
    put_result(m, result, challenges)
    m.save(out / "manifest.json")
    write_inventory(models_dir, [inventory_row(result)])
    return result
