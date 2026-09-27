"""Contracts and data quality rules: each rule class gets a clean pass, a violation and a refusal."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest
from ledger_bankgen.params import GeneratorParams
from ledger_contracts.ingest import dti_band
from ledger_contracts.rules import RULES, apply_rules, rules_for
from ledger_contracts.run import ContractError, _utf8, balance_roll_check, validate
from ledger_contracts.schemas import GENERATED, REAL, SPARKOV


def _postings(ids: list[int], amounts: list[float] | None = None) -> pl.DataFrame:
    n = len(ids)
    return pl.DataFrame(
        {
            "posting_id": ids,
            "transaction_id": list(range(n)),
            "source_type": ["deposit_entry"] * n,
            "source_id": list(range(n)),
            "gl_account": ["2000"] * n,
            "amount": amounts or [10.0] * n,
            "posted_at": [datetime(2026, 1, 5)] * n,
            "month": ["2026-01"] * n,
        }
    )


def test_every_rule_has_a_statement_and_a_known_severity() -> None:
    names = [r.name for r in RULES]
    assert len(names) == len(set(names))
    for rule in RULES:
        assert rule.severity in {"quarantine", "flag"}
        assert len(rule.statement) > 20


def test_duplicate_posting_rule_clean_pass() -> None:
    kept, quarantined, hits = apply_rules(_postings([1, 2, 3]), "gl_postings")
    assert kept.height == 3 and quarantined.height == 0
    assert {h["rule"]: h["rows_hit"] for h in hits}["posting_duplicate"] == 0


def test_duplicate_posting_rule_catches_and_keeps_the_first() -> None:
    kept, quarantined, hits = apply_rules(_postings([1, 2, 2, 3, 3, 3]), "gl_postings")
    assert kept["posting_id"].to_list() == [1, 2, 3]
    assert quarantined.height == 3
    assert set(quarantined["quarantine_rule"].to_list()) == {"posting_duplicate"}
    assert {h["rule"]: h["rows_hit"] for h in hits}["posting_duplicate"] == 3


def test_zero_posting_is_quarantined_under_its_own_rule() -> None:
    kept, quarantined, _ = apply_rules(_postings([1, 2], [10.0, 0.0]), "gl_postings")
    assert kept.height == 1
    assert quarantined["quarantine_rule"].to_list() == ["posting_zero_amount"]


def test_rules_refuse_an_empty_table() -> None:
    with pytest.raises(ValueError, match="empty"):
        apply_rules(_postings([]).clear(), "gl_postings")


def test_flag_rules_keep_the_row() -> None:
    entries = pl.DataFrame(
        {
            "txn_type": ["INTERNAL_TRANSFER", "INTERNAL_TRANSFER", "CARD_SPEND"],
            "counterparty_account_id": [None, "A0000002", None],
            "posted_at": [datetime(2026, 1, 1)] * 3,
        }
    )
    kept, quarantined, hits = apply_rules(entries, "deposit_entries")
    assert kept.height == 3 and quarantined.height == 0
    assert {h["rule"]: h["rows_hit"] for h in hits}["transfer_without_counterparty"] == 1


def test_balance_roll_check_finds_a_balance_that_does_not_roll() -> None:
    balances = pl.DataFrame(
        {
            "account_id": ["A1", "A1", "A2"],
            "month": ["2026-01", "2026-02", "2026-01"],
            "opening_balance": [100.0, 150.0, 20.0],
            "closing_balance": [150.0, 260.0, 20.0],
        }
    )
    entries = pl.DataFrame(
        {
            "account_id": ["A1", "A1", "A1"],
            "month": ["2026-01", "2026-02", "2026-02"],
            "amount": [50.0, 5.0, 5.0],
        }
    )
    checked = balance_roll_check(balances, entries)
    assert checked["balance_rolls"].to_list() == [True, False, True]
    assert checked["closing_from_entries"].to_list() == [150.0, 160.0, 20.0]


def test_contract_violation_stops_the_stage() -> None:
    bad = pl.DataFrame({"month": ["2026-13x"], "unemployment_rate": [4.0], "policy_rate": [3.0]})
    with pytest.raises(ContractError):
        validate(bad, GENERATED["macro_path"])


def test_contract_clean_pass_on_generated_tables(small_bank: tuple[Path, Path, GeneratorParams]) -> None:
    raw, _, _ = small_bank
    for table, schema in GENERATED.items():
        validate(_utf8(pl.read_parquet(raw / f"{table}.parquet")), schema)


def test_injected_defects_are_caught_at_the_injected_count(
    small_bank: tuple[Path, Path, GeneratorParams],
) -> None:
    raw, truth, _ = small_bank
    injected = {r["defect"]: r["count"] for r in pl.read_parquet(truth / "truth_defects.parquet").to_dicts()}
    _, _, hits = apply_rules(_utf8(pl.read_parquet(raw / "gl_postings.parquet")), "gl_postings")
    assert {h["rule"]: h["rows_hit"] for h in hits}["posting_duplicate"] == injected["duplicated_posting"]
    entries = _utf8(pl.read_parquet(raw / "deposit_entries.parquet"))
    _, _, hits = apply_rules(entries, "deposit_entries")
    found = {h["rule"]: h["rows_hit"] for h in hits}["transfer_without_counterparty"]
    assert found == injected["transfer_without_counterparty"]
    checked = balance_roll_check(_utf8(pl.read_parquet(raw / "deposit_balances.parquet")), entries)
    assert int((~checked["balance_rolls"]).sum()) == injected["balance_does_not_roll"]


def test_clean_bank_has_no_defects(clean_bank: tuple[Path, Path, GeneratorParams]) -> None:
    raw, _, _ = clean_bank
    entries = _utf8(pl.read_parquet(raw / "deposit_entries.parquet"))
    checked = balance_roll_check(_utf8(pl.read_parquet(raw / "deposit_balances.parquet")), entries)
    assert bool(checked["balance_rolls"].all())
    _, quarantined, _ = apply_rules(_utf8(pl.read_parquet(raw / "gl_postings.parquet")), "gl_postings")
    assert quarantined.height == 0


def test_every_real_and_stream_contract_names_itself() -> None:
    assert SPARKOV.name == "card_transactions"
    for name, schema in REAL.items():
        assert schema.name == name


def test_real_dataset_rules_count_publisher_codes() -> None:
    uci = pl.DataFrame({"education": [1, 0, 5, 2], "marriage": [1, 1, 2, 0]})
    _, _, hits = apply_rules(uci, "uci_default")
    assert hits[0]["rows_hit"] == 3
    assert rules_for("uci_default")[0].severity == "flag"


@pytest.mark.parametrize(
    ("value", "band"),
    [
        ("<20%", "<20%"),
        ("36", "36%-<50%"),
        ("49", "36%-<50%"),
        ("50%-60%", "50%-60%"),
        ("Exempt", None),
        ("NA", None),
    ],
)
def test_hmda_dti_bands(value: str, band: str | None) -> None:
    assert dti_band(value) == band


def test_schema_dates_are_dates() -> None:
    frame = pl.DataFrame(
        {
            "customer_id": ["C1"],
            "open_date": [date(2020, 1, 1)],
            "birth_year": [1980],
            "state": ["NJ"],
            "county_fips": ["34013"],
            "segment": ["mass"],
            "annual_income": [52000.0],
        }
    )
    validate(frame, GENERATED["customers"])
