"""Normalise the real public datasets into typed, staged tables.

Every reduction made here is stated in data/PROVENANCE.md. Nothing is dropped
silently: codes a publisher uses for "not applicable" or "exempt" become nulls
with a companion flag column, so the data quality page can count them.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from ledger_core.paths import Paths

# HMDA fields published as text that carry numbers, and the codes that are not numbers.
HMDA_NUMERIC = (
    "loan_amount",
    "loan_to_value_ratio",
    "interest_rate",
    "rate_spread",
    "total_loan_costs",
    "total_points_and_fees",
    "origination_charges",
    "discount_points",
    "lender_credits",
    "loan_term",
    "prepayment_penalty_term",
    "intro_rate_period",
    "property_value",
    "income",
    "tract_population",
    "tract_minority_population_percent",
    "ffiec_msa_md_median_family_income",
    "tract_to_msa_income_percentage",
    "tract_owner_occupied_units",
    "tract_one_to_four_family_homes",
    "tract_median_age_of_housing_units",
)
HMDA_NON_NUMBERS = ("Exempt", "NA", "")
DTI_BAND_ORDER = (
    "<20%",
    "20%-<30%",
    "30%-<36%",
    "36%-<50%",
    "50%-60%",
    ">60%",
)


@dataclass(frozen=True)
class Staged:
    name: str
    rows: int
    path: Path


def _write(frame: pl.DataFrame, path: Path) -> Staged:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path, compression="zstd")
    return Staged(path.stem, frame.height, path)


def dti_band(value: str | None) -> str | None:
    """HMDA publishes debt to income as bands below 36 and above 49, and whole numbers between."""
    if value is None or value in HMDA_NON_NUMBERS:
        return None
    if value in DTI_BAND_ORDER:
        return value
    try:
        number = float(value)
    except ValueError:
        return None
    if 36 <= number < 50:
        return "36%-<50%"
    return None


def stage_hmda(p: Paths) -> Staged:
    frames = [
        pl.read_parquet(f) for f in sorted((p.external / "hmda").glob("hmda_lar_nj_*_actions_1-5.parquet"))
    ]
    if not frames:
        raise FileNotFoundError("no HMDA extracts under data/external/hmda; see data/PROVENANCE.md")
    lar = pl.concat(frames, how="diagonal_relaxed")
    exprs: list[pl.Expr] = []
    for col in HMDA_NUMERIC:
        if col not in lar.columns:
            continue
        text = pl.col(col).cast(pl.Utf8)
        exprs.append(
            pl.when(text.is_in(list(HMDA_NON_NUMBERS)) | text.is_null())
            .then(None)
            .otherwise(text.cast(pl.Float64, strict=False))
            .alias(col)
        )
        exprs.append(text.eq("Exempt").fill_null(False).alias(f"{col}_exempt"))
    lar = lar.with_columns(
        *exprs,
        pl.col("activity_year").cast(pl.Int32),
        pl.col("action_taken").cast(pl.Int8),
        pl.col("loan_type").cast(pl.Int8),
        pl.col("loan_purpose").cast(pl.Int16),
        pl.col("occupancy_type").cast(pl.Int8),
        pl.col("derived_dwelling_category").cast(pl.Utf8),
        dti_band=pl.col("debt_to_income_ratio").map_elements(dti_band, return_dtype=pl.Utf8),
        county_fips=pl.col("county_code").cast(pl.Utf8),
        denied=(pl.col("action_taken").cast(pl.Int8) == 3),
    )
    return _write(lar, p.staged / "real" / "hmda_lar.parquet")


def stage_cfpb(p: Paths) -> list[Staged]:
    src = p.external / "cfpb"
    narratives = pl.read_parquet(src / "cfpb_narratives_sample_2024-09_2026-08.parquet").with_columns(
        pl.col("date_received").str.to_date("%Y-%m-%d"),
        pl.col("date_sent_to_company").str.to_date("%Y-%m-%d", strict=False),
        month=pl.col("date_received").str.slice(0, 7),
        monetary_relief=(pl.col("company_response_to_consumer") == "Closed with monetary relief"),
        timely=(pl.col("timely_response") == "Yes"),
        narrative_chars=pl.col("consumer_complaint_narrative").str.len_chars(),
    )
    aggregations = json.loads((src / "cfpb_ccdb_aggregations_2024-09_2026-08.json").read_text())
    month_rows = []
    for month in aggregations["months"]:
        for product in month["product"]:
            month_rows.append(
                {"month": month["month"], "product": product["key"], "complaints": product["n"]}
            )
    volume = pl.DataFrame(month_rows, schema={"month": pl.Utf8, "product": pl.Utf8, "complaints": pl.Int64})
    company_rows = []
    for c in aggregations["companies"]:
        responses = {r["key"]: r["n"] for r in c["company_response"]}
        timely = {r["key"]: r["n"] for r in c["timely"]}
        top_product = max(c["product"], key=lambda r: r["n"])["key"] if c["product"] else None
        company_rows.append(
            {
                "company": c["company"],
                "complaints": c["total"],
                "monetary_relief": responses.get("Closed with monetary relief", 0),
                "non_monetary_relief": responses.get("Closed with non-monetary relief", 0),
                "explanation": responses.get("Closed with explanation", 0),
                "in_progress": responses.get("In progress", 0),
                "timely": timely.get("Yes", 0),
                "top_product": top_product,
            }
        )
    companies = pl.DataFrame(company_rows)
    issue_rows = []
    for month in aggregations["months"]:
        for issue in month.get("issue", []):
            issue_rows.append({"month": month["month"], "issue": issue["key"], "complaints": issue["n"]})
    archive = json.loads((src / "cfpb_archive_counts.json").read_text())
    arch_rows = []
    for export, counts in archive.items():
        for month, rows in counts["rows"].items():
            arch_rows.append(
                {
                    "export": export,
                    "month": month,
                    "complaints": rows,
                    "with_narrative": counts["narratives"].get(month, 0),
                }
            )
    archive_counts = (
        pl.DataFrame(arch_rows)
        .group_by("month")
        .agg(pl.col("complaints").sum(), pl.col("with_narrative").sum())
    )
    return [
        _write(narratives, p.staged / "real" / "cfpb_narratives.parquet"),
        _write(volume, p.staged / "real" / "cfpb_volume_by_product.parquet"),
        _write(companies, p.staged / "real" / "cfpb_companies.parquet"),
        _write(
            pl.DataFrame(issue_rows, schema={"month": pl.Utf8, "issue": pl.Utf8, "complaints": pl.Int64}),
            p.staged / "real" / "cfpb_volume_by_issue.parquet",
        ),
        _write(archive_counts.sort("month"), p.staged / "real" / "cfpb_archive_counts.parquet"),
    ]


def stage_fdic(p: Paths) -> list[Staged]:
    src = p.external / "fdic"
    inst = pl.read_csv(src / "fdic_institutions_all_20260925.csv", infer_schema_length=0).with_columns(
        pl.col("CERT").cast(pl.Int64),
        (pl.col("ACTIVE") == "1").alias("ACTIVE"),
        pl.col("ASSET").cast(pl.Float64, strict=False),
        pl.col("DEP").cast(pl.Float64, strict=False),
    )
    fin = pl.read_csv(src / "fdic_financials_ne_midatlantic_2023q3_2026q2.csv", infer_schema_length=20_000)
    fin = fin.with_columns(
        pl.col("REPDTE").cast(pl.Utf8).str.to_date("%Y%m%d").alias("report_date"),
    )
    return [
        _write(inst, p.staged / "real" / "fdic_institutions.parquet"),
        _write(fin, p.staged / "real" / "fdic_financials.parquet"),
    ]


UCI_RENAME = {
    "ID": "account_id",
    "LIMIT_BAL": "limit_bal",
    "SEX": "sex",
    "EDUCATION": "education",
    "MARRIAGE": "marriage",
    "AGE": "age",
    "PAY_0": "pay_status_1",
    "PAY_2": "pay_status_2",
    "PAY_3": "pay_status_3",
    "PAY_4": "pay_status_4",
    "PAY_5": "pay_status_5",
    "PAY_6": "pay_status_6",
    "default.payment.next.month": "default_next_month",
}


def stage_uci(p: Paths) -> Staged:
    archive = p.external / "uci" / "uci_default_of_credit_card_clients_kaggle_uciml.zip"
    with zipfile.ZipFile(archive) as z, z.open("UCI_Credit_Card.csv") as handle:
        # Some amounts are written in scientific notation (1e+05), so read as text and cast.
        frame = pl.read_csv(io.BytesIO(handle.read()), infer_schema_length=0)
    integer_cols = {"ID", "SEX", "EDUCATION", "MARRIAGE", "AGE", "PAY_0", "default.payment.next.month"}
    integer_cols |= {f"PAY_{i}" for i in range(2, 7)}
    frame = frame.with_columns(
        [
            pl.col(c).cast(pl.Float64).cast(pl.Int64) if c in integer_cols else pl.col(c).cast(pl.Float64)
            for c in frame.columns
        ]
    )
    rename = dict(UCI_RENAME)
    for i in range(1, 7):
        rename[f"BILL_AMT{i}"] = f"bill_amt_{i}"
        rename[f"PAY_AMT{i}"] = f"pay_amt_{i}"
    frame = frame.rename(rename).with_columns(
        pl.col("account_id").cast(pl.Int64), pl.col("default_next_month").cast(pl.Int8)
    )
    return _write(frame, p.staged / "real" / "uci_default.parquet")


def stage_baf(p: Paths) -> Staged:
    parts = []
    for variant, name in (
        ("base", "baf_base_sample300k_seed20260831.parquet"),
        ("variant_ii", "baf_variant_ii_sample300k_seed20260831.parquet"),
    ):
        parts.append(pl.read_parquet(p.external / "baf" / name).with_columns(variant=pl.lit(variant)))
    return _write(pl.concat(parts), p.staged / "real" / "baf.parquet")


def stage_macro(p: Paths) -> list[Staged]:
    src = p.external / "macro"
    bls = pl.read_csv(src / "bls_series_2017_2026.csv", infer_schema_length=0).filter(
        pl.col("period").str.starts_with("M") & (pl.col("period") != "M13")
    )
    names = {
        "LNS14000000": "unemployment_us",
        "LASST340000000000003": "unemployment_nj",
        "CUSR0000SA0": "cpi_u",
    }
    bls = bls.with_columns(
        month=pl.col("year") + "-" + pl.col("period").str.slice(1, 2),
        series=pl.col("series_id").replace_strict(names),
        value=pl.col("value").cast(pl.Float64, strict=False),
    ).select("month", "series", "value")
    monthly = bls.pivot(on="series", index="month", values="value").sort("month")
    treasury = pl.read_csv(src / "treasury_par_yield_monthly_mean_2017_2026.csv").select(
        "month",
        pl.col("y_3mo").alias("treasury_3m"),
        pl.col("y_2yr").alias("treasury_2y"),
        pl.col("y_10yr").alias("treasury_10y"),
    )
    effr = pl.read_csv(src / "nyfed_effr_monthly_mean_2017_2026.csv").select(
        "month", pl.col("effr_mean").alias("fed_funds_effective")
    )
    hpi = pl.read_csv(
        src / "fhfa_hpi_purchase_only_usa_monthly_nj_quarterly_2015_2026.csv", infer_schema_length=0
    )
    hpi_us = hpi.filter(pl.col("frequency") == "monthly").select(
        month=pl.col("yr") + "-" + pl.col("period").str.zfill(2),
        hpi_us_sa=pl.col("index_sa").cast(pl.Float64),
    )
    monthly = (
        monthly.join(treasury, on="month", how="left")
        .join(effr, on="month", how="left")
        .join(hpi_us, on="month", how="left")
        .sort("month")
    )
    hpi_nj = hpi.filter(pl.col("frequency") == "quarterly").select(
        quarter=pl.col("yr") + "Q" + pl.col("period"), hpi_nj_nsa=pl.col("index_nsa").cast(pl.Float64)
    )
    chgdel = pl.read_csv(src / "frb_chgdel_sa_2015_2026.csv").with_columns(
        pl.col("quarter_start").str.to_date("%Y-%m-%d")
    )
    return [
        _write(monthly, p.staged / "real" / "macro_monthly.parquet"),
        _write(hpi_nj, p.staged / "real" / "fhfa_hpi_nj_quarterly.parquet"),
        _write(chgdel, p.staged / "real" / "frb_charge_off_delinquency.parquet"),
    ]


SCENARIO_COLUMNS = {
    "Scenario Name": "scenario",
    "Date": "quarter",
    "Real GDP growth": "real_gdp_growth",
    "Unemployment rate": "unemployment_rate",
    "CPI inflation rate": "cpi_inflation",
    "3-month Treasury rate": "treasury_3m",
    "5-year Treasury yield": "treasury_5y",
    "10-year Treasury yield": "treasury_10y",
    "BBB corporate yield": "bbb_yield",
    "Mortgage rate": "mortgage_rate",
    "Prime rate": "prime_rate",
    "House Price Index (Level)": "house_price_index",
    "Commercial Real Estate Price Index (Level)": "cre_price_index",
    "Market Volatility Index (Level)": "vix",
}


def stage_scenarios(p: Paths) -> Staged:
    parts = []
    for path in sorted((p.external / "scenarios").glob("2026_Final_*.csv")):
        frame = pl.read_csv(path, infer_schema_length=0)
        keep = [c for c in frame.columns if c in SCENARIO_COLUMNS]
        # The published files end with an empty line that reads as an all null row.
        frame = (
            frame.select(keep)
            .rename({c: SCENARIO_COLUMNS[c] for c in keep})
            .filter(pl.col("scenario").is_not_null())
        )
        numeric = [c for c in frame.columns if c not in {"scenario", "quarter"}]
        frame = frame.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in numeric])
        parts.append(frame)
    scen = pl.concat(parts, how="diagonal_relaxed").with_columns(
        quarter=pl.col("quarter").str.replace(" ", ""),
        scenario=pl.col("scenario").replace(
            {
                "Actual": "historic",
                "Supervisory Baseline": "baseline",
                "Supervisory Severely Adverse": "severely_adverse",
            }
        ),
    )
    return _write(scen, p.staged / "real" / "frb_scenarios.parquet")


def stage_all(p: Paths) -> list[Staged]:
    staged: list[Staged] = [stage_hmda(p)]
    staged += stage_cfpb(p)
    staged += stage_fdic(p)
    staged.append(stage_uci(p))
    staged.append(stage_baf(p))
    staged += stage_macro(p)
    staged.append(stage_scenarios(p))
    return staged
