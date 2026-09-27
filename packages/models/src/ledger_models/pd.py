"""Probability of default: the weight of evidence scorecard (champion) and the monotone GBM (challenger).

Prediction time is the application date. The outcome is default (90 days past due
or charge off) within twelve months of origination, censored by the calendar: only
loans originated at least twelve months before the as of month have one. The split
is by origination month, never random, so the test sample is later than anything
the model saw:

    development  2023-09 to 2024-08
    validation   2024-09 to 2025-02   (the loose underwriting vintages)
    test         2025-03 to 2025-08   (the recession quarter's originations)

Both models see only the application's credit characteristics. Age, ZIP code and
county sit in the applications table for the fairness audit and never reach a model.
The challenger is shadow scored on every application, including declines, and is
promoted only if it clears every gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
from ledger_scorecard.binning import coarse_classing, fine_classing
from ledger_scorecard.scorecard import (
    Scaling,
    Scorecard,
    adverse_action_reasons,
    check_proxies,
    fit_scorecard,
    psi,
)
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ledger_models.evaluate import Discrimination, discrimination, subgroup_table

NUMERIC = [
    "bureau_score",
    "dti",
    "revolving_utilization",
    "delinquencies_24m",
    "inquiries_6m",
    "oldest_trade_months",
    "employment_months",
    "annual_income",
    "loan_amount",
    "term_months",
]
CATEGORICAL = ["purpose", "housing_status", "channel"]
FEATURES = NUMERIC + CATEGORICAL

UCI_NUMERIC = [
    "limit_bal",
    "pay_status_1",
    "pay_status_2",
    "pay_status_3",
    "months_delinquent_6m",
    "utilization_1",
    "payment_ratio_1",
    "payment_ratio_avg",
    "bill_growth_6m",
    "pay_amt_1",
]


def split_of(month_index: int) -> str:
    if month_index <= 11:
        return "development"
    if month_index <= 17:
        return "validation"
    return "test"


def split_expr(month_index: pl.Expr) -> pl.Expr:
    return (
        pl.when(month_index <= 11)
        .then(pl.lit("development"))
        .when(month_index <= 17)
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
    )


def age_band_expr(age: pl.Expr) -> pl.Expr:
    return (
        pl.when(age < 25)
        .then(pl.lit("18 to 24"))
        .when(age < 35)
        .then(pl.lit("25 to 34"))
        .when(age < 50)
        .then(pl.lit("35 to 49"))
        .when(age < 65)
        .then(pl.lit("50 to 64"))
        .otherwise(pl.lit("65 and over"))
    )


def age_band(age: int) -> str:
    if age < 25:
        return "18 to 24"
    if age < 35:
        return "25 to 34"
    if age < 50:
        return "35 to 49"
    if age < 65:
        return "50 to 64"
    return "65 and over"


@dataclass
class PdData:
    booked: pl.DataFrame  # booked loans with an observed outcome, split assigned
    applications: pl.DataFrame  # every application, for shadow scoring and the audit


def load_generated(con: object) -> PdData:
    import duckdb

    assert isinstance(con, duckdb.DuckDBPyConnection)
    apps = con.execute(
        f"""
        select a.application_id, a.application_date, a.month, a.decision, a.booked, a.applicant_age,
            a.legacy_score, {", ".join("a." + c for c in FEATURES)},
            o.loan_id, o.default_12m, o.origination_index
        from staging.stg_loan_applications as a
        left join marts.mart_loan_outcomes as o using (application_id)
        order by a.application_date, a.application_id
        """
    ).pl()
    apps = apps.with_columns(
        age_band=age_band_expr(pl.col("applicant_age")),
    )
    booked = apps.filter(pl.col("default_12m").is_not_null()).with_columns(
        split=split_expr(pl.col("origination_index")),
        bad=pl.col("default_12m").cast(pl.Int8),
    )
    return PdData(booked=booked, applications=apps)


def load_uci(path: Path, seed: int) -> pl.DataFrame:
    """The UCI accounts with the engineered characteristics and a stratified random split.

    The data has no dates, so the split is random by necessity, stratified on the
    outcome, and stated as a limitation: it cannot show drift.
    """
    frame = pl.read_parquet(path)
    bills = [f"bill_amt_{i}" for i in range(1, 7)]
    pays = [f"pay_amt_{i}" for i in range(1, 7)]
    status = [f"pay_status_{i}" for i in range(1, 7)]
    frame = frame.with_columns(
        months_delinquent_6m=pl.sum_horizontal([(pl.col(c) > 0).cast(pl.Int32) for c in status]),
        utilization_1=pl.col("bill_amt_1") / pl.col("limit_bal"),
        payment_ratio_1=pl.when(pl.col("bill_amt_1") > 0)
        .then(pl.col("pay_amt_1") / pl.col("bill_amt_1"))
        .otherwise(None),
        payment_ratio_avg=pl.when(pl.sum_horizontal(bills) > 0)
        .then(pl.sum_horizontal(pays) / pl.sum_horizontal(bills))
        .otherwise(None),
        bill_growth_6m=(pl.col("bill_amt_1") - pl.col("bill_amt_6")) / pl.col("limit_bal"),
        bad=pl.col("default_next_month").cast(pl.Int8),
        age_band=age_band_expr(pl.col("age")),
    )
    rng = np.random.default_rng(seed)
    u = rng.random(frame.height)
    bad = frame["bad"].to_numpy()
    split = np.empty(frame.height, dtype=object)
    for cls in (0, 1):
        idx = np.flatnonzero(bad == cls)
        order = idx[np.argsort(u[idx])]
        n = len(order)
        split[order[: int(0.6 * n)]] = "development"
        split[order[int(0.6 * n) : int(0.8 * n)]] = "validation"
        split[order[int(0.8 * n) :]] = "test"
    return frame.with_columns(split=pl.Series(split.tolist(), dtype=pl.Utf8))


@dataclass
class Fitted:
    card: Scorecard
    challenger: lgb.Booster | None
    challenger_features: list[str]
    logistic: LogisticRegression
    scaler: StandardScaler
    logistic_columns: list[str]
    constraints: dict[str, int]
    fine_bins: dict[str, list[dict[str, object]]]
    levels: dict[str, list[str]]


def _design(
    frame: pl.DataFrame, numeric: list[str], categorical: list[str], levels: dict[str, list[str]]
) -> np.ndarray:
    cols = [
        frame[c].cast(pl.Float64).fill_null(frame[c].cast(pl.Float64).median()).to_numpy() for c in numeric
    ]
    for c in categorical:
        values = frame[c].to_list()
        for level in levels[c][1:]:
            cols.append(np.array([1.0 if v == level else 0.0 for v in values]))
    return np.column_stack(cols)


def _lgb_frame(
    frame: pl.DataFrame, numeric: list[str], categorical: list[str], levels: dict[str, list[str]]
) -> np.ndarray:
    cols = [frame[c].cast(pl.Float64).to_numpy() for c in numeric]
    for c in categorical:
        mapping = {v: float(i) for i, v in enumerate(levels[c])}
        cols.append(np.array([mapping.get(v, np.nan) for v in frame[c].to_list()], dtype=float))
    return np.column_stack(cols)


def fit_all(
    dev: pl.DataFrame,
    val: pl.DataFrame,
    *,
    numeric: list[str],
    categorical: list[str],
    scaling: Scaling,
    cutoff: float,
    proxies: set[str],
    iv_floor: float,
    correlation_ceiling: float,
    min_bin_share: float,
    max_fine_bins: int,
    seed: int,
) -> Fitted:
    features = numeric + categorical
    check_proxies(features, proxies)
    card = fit_scorecard(
        dev,
        "bad",
        features,
        categorical=set(categorical),
        scaling=scaling,
        cutoff=cutoff,
        proxies=proxies,
        iv_floor=iv_floor,
        correlation_ceiling=correlation_ceiling,
        min_bin_share=min_bin_share,
        max_fine_bins=max_fine_bins,
    )
    y_dev = dev["bad"].to_numpy()
    fine_bins: dict[str, list[dict[str, object]]] = {}
    for c in numeric:
        fine = fine_classing(dev[c].to_numpy(), y_dev.astype(float), c, max_bins=max_fine_bins)
        fine_bins[c] = [
            {"lower": b.lower, "upper": b.upper, "missing": b.is_missing, "goods": b.goods, "bads": b.bads}
            for b in fine.bins
        ]
    levels = {c: sorted({str(v) for v in dev[c].to_list()}) for c in categorical}
    # Monotone constraints follow the scorecard: where WoE rises with the value, risk falls.
    constraints: dict[str, int] = {}
    for c in numeric:
        coarse = coarse_classing(
            fine_classing(dev[c].to_numpy(), y_dev.astype(float), c, max_bins=max_fine_bins),
            min_bin_share=min_bin_share,
        )
        constraints[c] = -coarse.direction if len(coarse.ordered()) > 1 else 0
    x_dev = _lgb_frame(dev, numeric, categorical, levels)
    x_val = _lgb_frame(val, numeric, categorical, levels)
    params = {
        "objective": "binary",
        "learning_rate": 0.03,
        "num_leaves": 7,
        "min_data_in_leaf": 150,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 5.0,
        "monotone_constraints": [constraints[c] for c in numeric] + [0] * len(categorical),
        "monotone_constraints_method": "advanced",
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 2,
        "verbose": -1,
    }
    train = lgb.Dataset(
        x_dev,
        dev["bad"].to_numpy(),
        feature_name=features,
        categorical_feature=list(range(len(numeric), len(features))),
        free_raw_data=False,
    )
    valid = lgb.Dataset(x_val, val["bad"].to_numpy(), reference=train)
    booster = lgb.train(
        params,
        train,
        num_boost_round=600,
        valid_sets=[valid],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    scaler = StandardScaler()
    lvl = {c: levels[c] for c in categorical}
    design = _design(dev, numeric, categorical, lvl)
    logistic = LogisticRegression(max_iter=5000, C=1.0)
    logistic.fit(scaler.fit_transform(design), dev["bad"].to_numpy())
    return Fitted(
        card, booster, features, logistic, scaler, numeric + categorical, constraints, fine_bins, levels
    )


def predict(
    f: Fitted, frame: pl.DataFrame, numeric: list[str], categorical: list[str]
) -> dict[str, np.ndarray]:
    levels = f.levels
    champion = f.card.probability(frame)
    challenger = (
        f.challenger.predict(_lgb_frame(frame, numeric, categorical, levels)) if f.challenger else champion
    )
    design = _design(frame, numeric, categorical, {c: levels[c] for c in categorical})
    logistic = f.logistic.predict_proba(f.scaler.transform(design))[:, 1]
    return {
        "champion": champion,
        "challenger": np.asarray(challenger),
        "logistic": logistic,
        "score": f.card.score(frame),
    }


def evaluate_samples(
    frame: pl.DataFrame, preds: dict[str, np.ndarray], key: str
) -> dict[str, Discrimination]:
    out = {}
    for sample in ("development", "validation", "test"):
        mask = (frame["split"] == sample).to_numpy()
        out[sample] = discrimination(frame["bad"].to_numpy()[mask], preds[key][mask])
    return out


def base_rate_discrimination(frame: pl.DataFrame) -> Discrimination:
    dev_rate = float(frame.filter(pl.col("split") == "development")["bad"].mean())  # type: ignore[arg-type]
    test = frame.filter(pl.col("split") == "test")
    y = test["bad"].to_numpy()
    # A constant prediction ranks nothing; ties give an AUROC of one half by definition.
    return discrimination(y, np.full(y.size, dev_rate))


def audit_by_age(frame: pl.DataFrame, pd_col: np.ndarray, approved: np.ndarray) -> pl.DataFrame:
    """Approval rate, adverse impact ratio against the most approved band, AUROC and calibration by age band."""
    y = frame["bad"].to_numpy().astype(float)
    groups = frame["age_band"].to_numpy()
    table = subgroup_table(y, pd_col, groups)
    rates = []
    for g in table["group"].to_list():
        mask = groups == g
        rates.append(float(approved[mask].mean()))
    table = table.with_columns(approval_rate=pl.Series(rates))
    best = max(rates)
    return table.with_columns(adverse_impact_ratio=pl.col("approval_rate") / best)


def rank_agreement(a: np.ndarray, b: np.ndarray) -> float:
    return float(spearmanr(a, b).statistic)


def stability(dev_scores: np.ndarray, other: np.ndarray) -> float:
    return psi(dev_scores, other)


def reasons_for(
    card: Scorecard, frame: pl.DataFrame, reason_text: dict[str, str], proxies: set[str], top: int
) -> list[list[str]]:
    out = []
    for i in range(frame.height):
        rs = adverse_action_reasons(card, frame.slice(i, 1), reason_text, proxies, top=top)
        out.append([r.characteristic for r in rs])
    return out


def save_fitted(f: Fitted, folder: Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    f.card.save(folder / f"scorecard_{name}.json")
    (folder / f"fine_bins_{name}.json").write_text(json.dumps(f.fine_bins, indent=1) + "\n")
    if f.challenger is not None:
        f.challenger.save_model(str(folder / f"challenger_{name}.txt"))
