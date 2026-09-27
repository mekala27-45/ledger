"""Check the real datasets under data/external against their recorded hashes.

Row level real data is not committed (see data/PROVENANCE.md). This script
tells a new reader exactly what is present, what is missing, and how to get
each missing file, and fails if a present file's hash differs from the one the
published figures were computed from.

    uv run python scripts/fetch_external.py
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Expected:
    path: str
    sha256_prefix: str
    how: str


EXPECTED = (
    Expected(
        "hmda/hmda_lar_nj_2024_actions_1-5.parquet",
        "3a8a40f7c00e0787",
        "HMDA Data Browser (ffiec.cfpb.gov/data-browser): state NJ, year 2024, action taken 1 to 5; "
        "save the CSV and convert to parquet with every column as text",
    ),
    Expected(
        "hmda/hmda_lar_nj_2025_actions_1-5.parquet",
        "06479379492da08e",
        "HMDA Data Browser: state NJ, year 2025, action taken 1 to 5; same conversion",
    ),
    Expected(
        "cfpb/cfpb_ccdb_aggregations_2024-09_2026-08.json",
        "827e64bf18ab4d8c",
        "CFPB complaint search API aggregations for 2024-09-01 to 2026-08-31 (see PROVENANCE.md)",
    ),
    Expected(
        "cfpb/cfpb_narratives_sample_2024-09_2026-08.parquet",
        "1cc3ef852a4a4310",
        "CFPB export archive files CCDB_Export_7 to CCDB_Export_21, sampled as PROVENANCE.md states",
    ),
    Expected(
        "cfpb/cfpb_archive_counts.json", "aa419a7993c5a6d0", "counts per month from the same archive files"
    ),
    Expected(
        "fdic/fdic_institutions_all_20260925.csv",
        "abd6b2904a8e7919",
        "banks.data.fdic.gov/api/institutions, all institutions, active and inactive",
    ),
    Expected(
        "fdic/fdic_financials_ne_midatlantic_2023q3_2026q2.csv",
        "9489c075f194453d",
        "banks.data.fdic.gov/api/financials, CT DE MA MD NJ NY PA, 2023-09-30 to 2026-06-30",
    ),
    Expected(
        "uci/uci_default_of_credit_card_clients_kaggle_uciml.zip",
        "841af51be5c1e603",
        "kaggle.com/datasets/uciml/default-of-credit-card-clients-dataset (UCI dataset 350)",
    ),
    Expected(
        "baf/baf_base_sample300k_seed20260831.parquet",
        "1191924d5c02b78b",
        "Kaggle sgpjesus/bank-account-fraud-dataset-neurips-2022 Base.csv, 300,000 row sample, seed 20260831",
    ),
    Expected(
        "baf/baf_variant_ii_sample300k_seed20260831.parquet",
        "26cf76624ec63715",
        "same page, Variant II.csv, same sampling",
    ),
    Expected(
        "macro/bls_series_2017_2026.csv",
        "eff8cbf7fbb9d8ce",
        "BLS series LNS14000000, LASST340000000000003, CUSR0000SA0, 2017 to 2026",
    ),
    Expected(
        "macro/fhfa_hpi_purchase_only_usa_monthly_nj_quarterly_2015_2026.csv",
        "63dba4801727afea",
        "FHFA HPI master file, purchase only, USA monthly and NJ quarterly",
    ),
    Expected(
        "macro/treasury_par_yield_monthly_mean_2017_2026.csv",
        "bb5256ef96a542ad",
        "Treasury daily par yield curve rates, averaged by month",
    ),
    Expected(
        "macro/nyfed_effr_monthly_mean_2017_2026.csv",
        "376d0e4b5355f496",
        "New York Fed effective federal funds rate, averaged by month",
    ),
    Expected(
        "macro/frb_chgdel_sa_2015_2026.csv",
        "ea5c72be12acde91",
        "Federal Reserve Board charge off and delinquency rates, seasonally adjusted",
    ),
    Expected("macro/frb_chgdel_series_map.csv", "8b0491b62459b8ce", "series ids for the file above"),
    Expected(
        "scenarios/2026_Final_Supervisory_Baseline_Domestic.csv",
        "4d798f6f059bc9a9",
        "Federal Reserve Board 2026 stress test scenarios, domestic baseline",
    ),
    Expected(
        "scenarios/2026_Final_Supervisory_Severely_Adverse_Domestic.csv",
        "10cd1bc9c3397a1c",
        "Federal Reserve Board 2026 stress test scenarios, domestic severely adverse",
    ),
    Expected(
        "scenarios/2026_Final_Historic_Domestic_2015_2025.csv",
        "744cbd326e7fbcbf",
        "Federal Reserve Board 2026 stress test scenarios, historical domestic series",
    ),
)


def sha_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def check(root: Path = ROOT) -> tuple[list[str], list[str], list[str]]:
    base = root / "data" / "external"
    present, missing, changed = [], [], []
    for item in EXPECTED:
        path = base / item.path
        if not path.exists():
            missing.append(f"{item.path}\n    {item.how}")
        elif sha_prefix(path) != item.sha256_prefix:
            changed.append(item.path)
        else:
            present.append(item.path)
    return present, missing, changed


def main() -> int:
    present, missing, changed = check()
    print(f"{len(present)} of {len(EXPECTED)} real files present and matching their recorded hash")
    for line in missing:
        print(f"missing: {line}")
    for line in changed:
        print(f"hash differs from the one the published figures used: {line}")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
