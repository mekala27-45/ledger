# Data provenance

Every dataset this repository reads, where it came from, when, under what terms,
and what was done to it before the warehouse saw it. Row level real data is not
committed; `make fetch` checks what is present against the hashes below and
prints the retrieval steps for anything missing. Generated data is not committed
either, because the seed rebuilds it byte for byte.

Hashes are the first sixteen hex characters of SHA-256 over the file as stored
under `data/external/`.

## Generated

### Harborline Bank core banking tables (`data/raw/generated`)

- **Source:** `packages/bankgen`, this repository's seeded generator.
- **Command:** `make generate` (seed 20260831, 50,000 customers, September 2023
  to August 2026). Every parameter is in `config/ledger.yaml` and
  `packages/bankgen/src/ledger_bankgen/params.py`.
- **Truth tables** (`data/raw/truth`): latent risk per customer and loan, the
  injected typology membership, the injected defects with counts, the ledger
  break and the attrition hazard. Only recovery tests, the typology scorecard
  and the reconciliation tests read them.
- **Licence:** Apache 2.0 with the code.

### Card transactions (`data/raw/sparkov`)

- **Source:** Sparkov Data Generation, github.com/namebrandon/Sparkov_Data_Generation,
  commit `b5eb45c89d36f2aa4ef16044a42945bed8b96d93`, MIT licence.
- **Command:** `uv run --group sparkov python scripts/run_sparkov.py --customers 1250 --start 2025-09-01 --end 2026-08-31`
  with seed 20260831 and Faker 13.12.0. The wrapper seeds `random`, numpy and
  Faker per chunk from the seed, the profile and the chunk offset, so the output
  does not depend on process pool scheduling. Sparkov itself is not modified.
- **Output:** 1,079,250 transactions on 1,243 cards, 11,898 labelled fraud,
  September 2025 to August 2026.
- **Reduction:** names, street, card number, account number, SSN, job and date
  of birth are dropped at ingest; the card number becomes a salted key and the
  date of birth a birth year. The generated full names are kept only in
  `data/staged/sparkov/person_names.txt.gz`, for the identifier scan.
- **Label delay:** Sparkov labels every transaction immediately. The censoring
  calendar adds the 60 day chargeback window; nothing here pretends Sparkov
  models it.

## Real

### HMDA loan application register, New Jersey, 2024 and 2025

- **Source:** FFIEC HMDA Data Browser, ffiec.cfpb.gov/data-browser, state NJ,
  one download per year with action taken 1 to 5 (originated, approved not
  accepted, denied, withdrawn, incomplete). Every field is kept.
- **Retrieved:** 26 September 2026.
- **Files:** `hmda/hmda_lar_nj_2024_actions_1-5.parquet` (289,315 rows,
  `3a8a40f7c00e0787`), `hmda/hmda_lar_nj_2025_actions_1-5.parquet` (320,098 rows,
  `06479379492da08e`), each the Data Browser CSV converted to parquet with every
  column kept as text.
- **Licence:** public domain (US government work).
- **Reduction at ingest:** numeric fields are cast; the codes `Exempt` and `NA`
  become nulls with an `_exempt` flag column so the data quality page counts
  them; debt to income is mapped to the bands HMDA publishes.

### CFPB Consumer Complaint Database

- **Aggregates:** the Bureau's complaint search API,
  consumerfinance.gov/data-research/consumer-complaints/search/api/v1/, date
  received 1 September 2024 to 31 August 2026 inclusive, monthly counts by
  product, sub product, issue, company response, timeliness and channel, plus the
  30 companies with the most complaints. 11,430,555 complaints in the window.
  Retrieved 27 September 2026. `cfpb/cfpb_ccdb_aggregations_2024-09_2026-08.json`
  (`827e64bf18ab4d8c`).
- **Narratives:** on 14 August 2026 the Bureau stopped serving narratives
  through the API. They come instead from its published export archive files
  CCDB_Export_7 through CCDB_Export_21, read locally. Complaints received in the
  window with a narrative (published only where the consumer consented) were
  sampled at about 2,000 per month by a salted hash of the complaint id, so the
  sample is reproducible and not ordered by anything in the complaint.
  46,084 narratives, `cfpb/cfpb_narratives_sample_2024-09_2026-08.parquet`
  (`1cc3ef852a4a4310`). Row and narrative counts per month for the archive
  files are in `cfpb/cfpb_archive_counts.json` (`aa419a7993c5a6d0`).
- **Known gap:** August 2026 narratives stop at the archive's cutoff, so the
  last month is thin. It is the same right censoring the fraud desk shows.
- **Licence:** the API metadata states CC0. The Bureau notes complaints are not
  a statistical sample of consumers' experiences; every page that uses them says so.

### FDIC BankFind Suite

- **Institution directory:** every FDIC insured institution, active and
  inactive, 27,834 rows, from banks.data.fdic.gov/api/institutions. Retrieved
  25 September 2026. `fdic/fdic_institutions_all_20260925.csv`
  (`abd6b2904a8e7919`). Names are committed as
  `data/reference/fdic_institution_names.csv.gz` for the bank name check.
- **Financials:** quarterly Call Report figures from
  banks.data.fdic.gov/api/financials for institutions in CT, DE, MA, MD, NJ, NY
  and PA, 30 September 2023 to 30 June 2026, 512 institutions, 5,871 rows.
  `fdic/fdic_financials_ne_midatlantic_2023q3_2026q2.csv` (`9489c075f194453d`).
  The peer group used on the executive page is a subset defined by asset size
  in `packages/functions/src/ledger_functions/f01_executive`.
- **Licence:** public domain (US government work).

### UCI Default of Credit Card Clients

- **Source:** I-Cheng Yeh, UCI Machine Learning Repository, dataset 350, via the
  Kaggle mirror uciml/default-of-credit-card-clients-dataset, all 30,000 rows.
  `uci/uci_default_of_credit_card_clients_kaggle_uciml.zip` (`841af51be5c1e603`).
- **Citation:** Yeh, I. C., and Lien, C. H. (2009). The comparisons of data
  mining techniques for the predictive accuracy of probability of default of
  credit card clients. Expert Systems with Applications, 36(2), 2473 to 2480.
- **Licence:** CC BY 4.0 at UCI.
- **Known issues:** EDUCATION codes 0, 5 and 6 and MARRIAGE code 0 are present
  but not in the codebook; counted by rule, kept.

### Bank Account Fraud suite (Feedzai, NeurIPS 2022)

- **Source:** kaggle.com/datasets/sgpjesus/bank-account-fraud-dataset-neurips-2022,
  the Base variant and Variant II.
- **Citation:** Jesus, S., Pombal, J., Alves, D., Cruz, A., Saleiro, P., Ribeiro,
  R. P., Gama, J., and Bizarro, P. (2022). Turning the Tables: Biased,
  Imbalanced, Dynamic Tabular Datasets for ML Evaluation. NeurIPS 2022 Datasets
  and Benchmarks.
- **Licence:** CC BY-NC-SA 4.0, as stated on the Kaggle page. Not committed.
- **Reduction:** a 300,000 row simple random sample of each million row
  variant, seed 20260831. `baf/baf_base_sample300k_seed20260831.parquet`
  (`1191924d5c02b78b`), `baf/baf_variant_ii_sample300k_seed20260831.parquet`
  (`26cf76624ec63715`).
- **Known issues:** negative values encode missing in several fields; counted by rule.

### Macroeconomic series, from their primary publishers

| File | Publisher | Series | Hash |
|---|---|---|---|
| `macro/bls_series_2017_2026.csv` | Bureau of Labor Statistics | LNS14000000 (US unemployment rate), LASST340000000000003 (New Jersey unemployment rate), CUSR0000SA0 (CPI-U) | `eff8cbf7fbb9d8ce` |
| `macro/fhfa_hpi_purchase_only_usa_monthly_nj_quarterly_2015_2026.csv` | Federal Housing Finance Agency | House Price Index, purchase only, USA monthly and NJ quarterly | `63dba4801727afea` |
| `macro/treasury_par_yield_monthly_mean_2017_2026.csv` | US Treasury | Daily par yield curve rates, averaged by month | `bb5256ef96a542ad` |
| `macro/nyfed_effr_monthly_mean_2017_2026.csv` | Federal Reserve Bank of New York | Effective federal funds rate, daily, averaged by month | `376d0e4b5355f496` |
| `macro/frb_chgdel_sa_2015_2026.csv` | Federal Reserve Board | Charge off and delinquency rates, all commercial banks, seasonally adjusted (series ids in `frb_chgdel_series_map.csv`, `8b0491b62459b8ce`) | `ea5c72be12acde91` |

All public domain. Retrieved 26 September 2026. FRED is not used and nothing
from FRED is committed, because its terms restrict redistribution.

- **Known gap:** BLS published no October 2025 figures for any of the three
  series; the release notes the 2025 lapse in appropriations. The month is null,
  never interpolated, and the data quality page counts it.

### Federal Reserve supervisory stress test scenarios, 2026

- **Source:** Federal Reserve Board, 2026 stress test scenarios, domestic
  variables: `2026_Final_Supervisory_Baseline_Domestic.csv` (`4d798f6f059bc9a9`),
  `2026_Final_Supervisory_Severely_Adverse_Domestic.csv` (`10cd1bc9c3397a1c`) and
  the historical series `2026_Final_Historic_Domestic_2015_2025.csv`
  (`744cbd326e7fbcbf`). 2026 Q1 to 2029 Q1.
- **Licence:** public domain.
- **Reduction:** a trailing empty line in each file reads as an all null row
  and is dropped at ingest; nothing else changes.

### County boundaries

- **Source:** us-atlas 3.0.1 (npm), `counties-10m.json`, derived from the US
  Census Bureau cartographic boundary files, public domain. The New Jersey
  counties are extracted at build time into `web/public/data/nj_counties.json`.
