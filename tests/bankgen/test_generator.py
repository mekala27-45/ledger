"""The generator's promises: double entry holds, sub ledgers tie to the ledger, seeds reproduce, truth is stated."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import polars as pl
from ledger_bankgen.generate import generate
from ledger_bankgen.params import GeneratorParams


def _con(raw: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for path in raw.glob("*.parquet"):
        con.execute(f"create view {path.stem} as select * from read_parquet('{path}')")
    return con


def test_every_month_of_postings_balances(clean_bank: tuple[Path, Path, GeneratorParams]) -> None:
    con = _con(clean_bank[0])
    worst = con.execute(
        "select max(abs(s)) from (select month, sum(amount::decimal(18, 2)) s from gl_postings group by month)"
    ).fetchone()[0]
    assert worst == 0


def test_every_journal_balances(clean_bank: tuple[Path, Path, GeneratorParams]) -> None:
    con = _con(clean_bank[0])
    worst = con.execute(
        "select max(abs(s)) from (select journal_id, sum(amount) s from gl_journals group by 1)"
    ).fetchone()[0]
    assert worst < 0.005


def test_deposit_sub_ledger_ties_to_the_ledger_when_clean(
    clean_bank: tuple[Path, Path, GeneratorParams],
) -> None:
    con = _con(clean_bank[0])
    rows = con.execute(
        """
        with sub as (
          select b.month, a.product, sum(b.closing_balance) as sub_balance
          from deposit_balances b join deposit_accounts a using (account_id) group by 1, 2),
        gl as (
          select month, gl_account, -sum(sum(amount)) over (partition by gl_account order by month) as gl_balance
          from gl_postings where gl_account in ('2000', '2010', '2020') group by 1, 2)
        select s.month, s.product, s.sub_balance, g.gl_balance
        from sub s join gl g on g.month = s.month
         and g.gl_account = case s.product when 'checking' then '2000' when 'savings' then '2010' else '2020' end
        """
    ).fetchall()
    assert rows
    for month, product, sub_balance, gl_balance in rows:
        assert abs(sub_balance - gl_balance) < 0.05, (month, product, sub_balance, gl_balance)


def test_every_posting_ties_to_a_source(clean_bank: tuple[Path, Path, GeneratorParams]) -> None:
    con = _con(clean_bank[0])
    orphans = con.execute(
        """
        select count(*) from gl_postings p
        where (p.source_type = 'deposit_entry' and p.source_id not in (select entry_id from deposit_entries))
           or (p.source_type = 'loan_event' and p.source_id not in (select event_id from loan_events))
           or (p.source_type = 'gl_journal' and p.source_id not in (select journal_id from gl_journals))
        """
    ).fetchone()[0]
    assert orphans == 0


def test_the_same_seed_reproduces_the_same_bank(tmp_path: Path) -> None:
    params = GeneratorParams().scaled(400)
    digests = []
    for run in ("a", "b"):
        generate(params, tmp_path / run / "raw", tmp_path / run / "truth", verbose=False)
        frame = pl.read_parquet(tmp_path / run / "raw" / "deposit_entries.parquet")
        digests.append(hashlib.sha256(frame.write_csv().encode()).hexdigest())
    assert digests[0] == digests[1]


def test_typology_membership_is_recorded(small_bank: tuple[Path, Path, GeneratorParams]) -> None:
    _, truth, params = small_bank
    t = pl.read_parquet(truth / "truth_typologies.parquet")
    kinds = set(t["typology"].unique())
    assert kinds == {"structuring", "rapid_movement", "mule", "round_tripping"}
    structuring = t.filter(pl.col("typology") == "structuring")
    assert structuring["customer_id"].n_unique() <= params.typologies.structuring_customers


def test_structuring_deposits_sit_under_the_threshold(small_bank: tuple[Path, Path, GeneratorParams]) -> None:
    raw, truth, _ = small_bank
    entries = pl.read_parquet(raw / "deposit_entries.parquet")
    episodes = pl.read_parquet(truth / "truth_typologies.parquet").filter(pl.col("typology") == "structuring")
    cash = entries.filter(
        (pl.col("txn_type") == "CASH_DEPOSIT") & pl.col("reference").is_in(episodes["episode_id"].to_list())
    )
    assert cash.height > 0
    assert cash["amount"].max() < 10_000


def test_defects_are_injected_and_counted(small_bank: tuple[Path, Path, GeneratorParams]) -> None:
    _, truth, _ = small_bank
    defects = {r["defect"]: r["count"] for r in pl.read_parquet(truth / "truth_defects.parquet").to_dicts()}
    assert set(defects) == {
        "duplicated_posting",
        "transfer_without_counterparty",
        "balance_does_not_roll",
        "ledger_break",
    }
    assert defects["duplicated_posting"] > 0


def test_ledger_break_is_in_reported_balances_only(small_bank: tuple[Path, Path, GeneratorParams]) -> None:
    raw, truth, params = small_bank
    brk = pl.read_parquet(truth / "truth_ledger_break.parquet").row(0, named=True)
    assert brk == {
        "gl_account": params.defects.ledger_break_account,
        "month": params.defects.ledger_break_month,
        "amount": params.defects.ledger_break_amount,
    }


def test_nothing_opens_after_the_as_of_date(small_bank: tuple[Path, Path, GeneratorParams]) -> None:
    import datetime as _dt

    raw, _, _ = small_bank
    as_of = _dt.date(2026, 8, 31)
    loans = pl.read_parquet(raw / "loans.parquet")
    assert loans.filter(pl.col("origination_date") > as_of).height == 0
    accounts = pl.read_parquet(raw / "deposit_accounts.parquet")
    assert accounts.filter(pl.col("open_date") > as_of).height == 0
