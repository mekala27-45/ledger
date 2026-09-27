"""Three trainers run end to end on small synthetic tables and leave a complete record.

The published models train on the full warehouse and on real data that is not
committed. These tests give each trainer tables of the same shape, built here with a
known signal, and check that it trains, gates, writes a manifest with every contract
line, and records its challenges. They do not check the published numbers; the claim
gate does that.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pytest
from ledger_core.config import load_config
from ledger_core.manifest import Manifest
from ledger_models.contract import CONTRACT_LINES

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    shutil.copy(ROOT / "DECISIONS.md", tmp_path / "DECISIONS.md")
    return tmp_path


def _check(models_dir: Path, model_id: str) -> Manifest:
    m = Manifest.load(models_dir / model_id / "manifest.json")
    contract = m.tables[f"models.{model_id}.contract"]
    assert [r[0] for r in contract.rows] == list(CONTRACT_LINES)
    assert len(m.tables[f"models.{model_id}.challenges"].rows) >= 2
    assert m.raw(f"models.{model_id}.conclusion") in {"approved", "approved with conditions", "not approved"}
    return m


def test_fraud_account_runs_the_baf_protocol(root: Path) -> None:
    from ledger_models import train_baf as baf

    rng = np.random.default_rng(1)
    frames = []
    for variant in ("base", "variant_ii"):
        n = 4000
        data: dict[str, object] = {c: rng.normal(size=n) for c in baf.NUMERIC}
        for c in baf.CATEGORICAL:
            data[c] = rng.choice(["AA", "AB", "AC"], size=n).tolist()
        age = rng.choice([20, 30, 40, 50, 60], size=n)
        risk = 1.5 * np.asarray(data["credit_risk_score"]) + 0.5 * (age >= 50)
        data["customer_age"] = age
        data["fraud_bool"] = (rng.random(n) < 1 / (1 + np.exp(-(-3.5 + risk)))).astype(int)
        data["month"] = np.repeat(np.arange(8), n // 8)
        data["variant"] = variant
        frames.append(pl.DataFrame(data))
    con = duckdb.connect()
    con.execute("create schema staging")
    table = pl.concat(frames)
    con.register("baf", table.to_arrow())
    con.execute("create table staging.stg_baf as select * from baf")
    cfg = load_config(ROOT / "config" / "ledger.yaml")
    result = baf.run(con, cfg, root, root / "models")
    m = _check(root / "models", "fraud_account")
    assert result.samples["test"].auroc > 0.7
    assert len(m.tables["models.fraud_account.variants"].rows) >= 10
    assert 0.0 < float(m.raw("models.fraud_account.ratio")) <= 1.0  # type: ignore[arg-type]


def _loans(n_loans: int, seed: int) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    rng = np.random.default_rng(seed)
    months = [f"{2023 + (8 + k) // 12}-{(8 + k) % 12 + 1:02d}" for k in range(36)]
    rows = []
    loans = []
    for i in range(n_loans):
        loan = f"N{i:06d}"
        product = rng.choice(["installment", "card", "mortgage"], p=[0.5, 0.4, 0.1])
        rate = float(rng.uniform(0.05, 0.25))
        loans.append(
            {"loan_id": loan, "interest_rate": rate, "credit_limit": 5000.0 if product == "card" else 0.0}
        )
        state, balance = "current", float(rng.uniform(1000, 20000))
        for k, month in enumerate(months):
            opening = state
            u = rng.random()
            if state == "current":
                state = "30" if u < 0.04 + rate / 10 else "current"
            elif state == "30":
                state = "current" if u < 0.45 else "60"
            elif state == "60":
                state = "current" if u < 0.25 else "90+"
            elif state == "90+":
                state = "current" if u < 0.1 else ("charged_off" if u > 0.7 else "90+")
            paid = 300.0 if state == "current" else (150.0 if u < 0.3 else 0.0)
            rows.append(
                {
                    "loan_id": loan,
                    "product": product,
                    "month": month,
                    "month_index": k,
                    "bucket_open": opening,
                    "bucket": state,
                    "months_on_book": k + 1,
                    "closing_balance": balance,
                    "scheduled_payment": 300.0,
                    "amount_paid": paid,
                }
            )
            if state == "charged_off":
                break
    macro = pl.DataFrame({"month": months, "unemployment_rate": np.linspace(4.0, 5.5, 36)})
    return pl.DataFrame(rows), pl.DataFrame(loans), macro


def test_cure_trains_against_the_bucket_rule(root: Path) -> None:
    from ledger_models import train_cure as cure

    loan_months, loans, macro = _loans(2500, seed=4)
    con = duckdb.connect()
    con.execute("create schema marts; create schema staging")
    for name, frame in (("lm", loan_months), ("ln", loans), ("mc", macro)):
        con.register(name, frame.to_arrow())
    con.execute("create table marts.fct_loan_month as select * from lm")
    con.execute("create table staging.stg_loans as select * from ln")
    con.execute("create table staging.stg_macro_path as select * from mc")
    cfg = load_config(ROOT / "config" / "ledger.yaml")
    result = cure.run(con, cfg, root, root / "models")
    m = _check(root / "models", "cure")
    assert result.samples["test"].auroc > 0.5
    assert m.raw("models.cure.leakage_rows") == 200
    assert pl.read_parquet(root / "models" / "cure" / "queue.parquet").height > 0


def test_relief_decides_whether_the_narrative_earns_its_place(root: Path) -> None:
    from ledger_nlp import train as relief

    rng = np.random.default_rng(9)
    months = [f"{2024 + (8 + k) // 12}-{(8 + k) % 12 + 1:02d}" for k in range(23)]
    n = 4600
    refund = rng.random(n) < 0.3
    words = np.where(
        refund, "the bank charged a fee twice and refused to refund it", "my report shows an account"
    )
    frame = pl.DataFrame(
        {
            "complaint_id": [str(i) for i in range(n)],
            "month": rng.choice(months, size=n).tolist(),
            "product": np.where(refund, "Checking or savings account", "Credit reporting").tolist(),
            "sub_product": [""] * n,
            "issue": rng.choice(["Managing an account", "Incorrect information"], size=n).tolist(),
            "company": rng.choice(["A BANK", "B BANK", "C BUREAU"], size=n).tolist(),
            "tags": rng.choice(["", "Older American", "Servicemember"], size=n).tolist(),
            "consumer_complaint_narrative": [f"{w} case {i}" for i, w in enumerate(words.tolist())],
            "monetary_relief": (refund & (rng.random(n) < 0.5)).tolist(),
            "company_response_to_consumer": ["Closed with explanation"] * n,
        }
    )
    staged = root / "data" / "staged" / "real"
    staged.mkdir(parents=True)
    frame.write_parquet(staged / "cfpb_narratives.parquet")
    cfg = load_config(ROOT / "config" / "ledger.yaml")
    relief.run(duckdb.connect(), cfg, root, root / "models")
    m = _check(root / "models", "relief")
    status = m.raw("models.relief.status")
    conclusion = m.raw("models.relief.conclusion")
    # Integrated only when approved; otherwise it stays in development.
    assert (status == "development") == (conclusion == "not approved")
    assert pl.read_parquet(root / "models" / "relief" / "issues.parquet").height > 0
