"""Each monitoring rule fires on its typology at the boundary, stays quiet just short of it,
and the evaluation counts only what posted."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import networkx as nx
import polars as pl
import pytest
from ledger_crime.evaluate import label_alerts, posted_truth, scorecard
from ledger_crime.network import communities
from ledger_crime.rules import AmlParams, mule, rapid_movement, round_tripping, run_rules, structuring

ROOT = Path(__file__).resolve().parents[2]
P = AmlParams(
    reporting_threshold=10_000.0,
    structuring_floor=8_000.0,
    structuring_window_days=10,
    rapid_movement_hours=24,
    mule_fan_in_min_counterparties=8,
    mule_window_days=14,
    cycle_max_length=5,
    cycle_window_days=14,
)
T0 = datetime(2026, 3, 2, 9, 0)
ENTRY_COLUMNS = (
    "entry_id bigint, posted_at timestamp, txn_type varchar, amount decimal(18,2), branch_id smallint, "
    "reference bigint, account_id varchar, customer_id varchar, counterparty_account_id varchar, counterparty_id varchar"
)


def warehouse(
    entries: list[tuple], accounts: list[tuple[str, str]] | None = None
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("create schema marts")
    con.execute(f"create table marts.fct_deposit_entry ({ENTRY_COLUMNS})")
    if entries:
        con.executemany("insert into marts.fct_deposit_entry values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", entries)
    con.execute(
        "create table marts.dim_deposit_account (account_id varchar, customer_id varchar, open_date date)"
    )
    for account, customer in accounts or []:
        con.execute(
            "insert into marts.dim_deposit_account values (?, ?, date '2020-01-01')", [account, customer]
        )
    con.execute(
        """
        create view marts.mart_transfer_edges as
        select entry_id, posted_at, txn_type, abs(amount) as amount,
            case when amount < 0 then account_id else coalesce(counterparty_account_id, counterparty_id) end as source_party,
            case when amount < 0 then coalesce(counterparty_account_id, counterparty_id) else account_id end as target_party,
            account_id, customer_id, amount > 0 as inbound
        from marts.fct_deposit_entry
        where not (txn_type = 'INTERNAL_TRANSFER' and amount > 0)
        """
    )
    return con


def cash(
    i: int, days: float, amount: float, branch: int = 1, account: str = "A1", ref: int | None = None
) -> tuple:
    return (i, T0 + timedelta(days=days), "CASH_DEPOSIT", amount, branch, ref, account, "C1", None, None)


def test_structuring_fires_on_three_deposits_under_the_threshold() -> None:
    con = warehouse([cash(1, 0, 9_000, 1), cash(2, 2, 8_500, 2), cash(3, 5, 9_900, 3)])
    alerts = structuring(con, P, "{count} deposits, ${total}")
    assert alerts.height == 1
    assert alerts["entries"][0] == 3
    assert alerts["branches"][0] == 3


def test_structuring_stays_quiet_below_the_count_or_outside_the_window() -> None:
    assert structuring(warehouse([cash(1, 0, 9_000), cash(2, 2, 8_500)]), P, "{count}").is_empty()
    spread = warehouse([cash(1, 0, 9_000), cash(2, 6, 8_500), cash(3, 12, 9_900)])
    assert structuring(spread, P, "{count}").is_empty()
    # A deposit at the threshold is reported by the bank anyway and is not structuring.
    at = warehouse([cash(1, 0, 10_000), cash(2, 1, 10_000), cash(3, 2, 10_000)])
    assert structuring(at, P, "{count}").is_empty()


def wire(i: int, hours: float, amount: float, kind: str, account: str = "A1") -> tuple:
    return (i, T0 + timedelta(hours=hours), kind, amount, None, None, account, "C1", None, f"X{i}")


def test_rapid_movement_fires_when_most_of_a_wire_leaves_within_hours() -> None:
    con = warehouse([wire(1, 0, 50_000, "WIRE_IN"), wire(2, 10, -45_000, "WIRE_OUT")])
    assert rapid_movement(con, P, "${inbound} ${outbound} {hours}").height == 1
    late = warehouse([wire(1, 0, 50_000, "WIRE_IN"), wire(2, 30, -45_000, "WIRE_OUT")])
    assert rapid_movement(late, P, "${inbound} ${outbound} {hours}").is_empty()
    small = warehouse([wire(1, 0, 50_000, "WIRE_IN"), wire(2, 10, -20_000, "WIRE_OUT")])
    assert rapid_movement(small, P, "${inbound} ${outbound} {hours}").is_empty()


def p2p(i: int, days: float, amount: float, sender: str) -> tuple:
    return (i, T0 + timedelta(days=days), "P2P_IN", amount, None, None, "A1", "C1", None, sender)


def test_mule_fires_on_many_senders_then_one_wire_out() -> None:
    senders = [p2p(i, i * 0.5, 1_500, f"X{i}") for i in range(8)]
    con = warehouse([*senders, wire(99, 24 * 6, -9_000, "WIRE_OUT")])
    assert mule(con, P, "{senders} {days} ${outbound}").height == 1
    fewer = warehouse([*senders[:7], wire(99, 24 * 6, -9_000, "WIRE_OUT")])
    assert mule(fewer, P, "{senders} {days} ${outbound}").is_empty()


def hop(i: int, days: float, amount: float, src: str, dst: str, ref: int | None = None) -> list[tuple]:
    at = T0 + timedelta(days=days)
    return [
        (i, at, "INTERNAL_TRANSFER", -amount, None, ref, src, f"C{src}", dst, None),
        (i + 1000, at, "INTERNAL_TRANSFER", amount, None, ref, dst, f"C{dst}", src, None),
    ]


RING = [("A1", "CA1"), ("A2", "CA2"), ("A3", "CA3")]


def test_round_tripping_fires_on_a_ring_that_comes_home() -> None:
    entries = hop(1, 0, 20_000, "A1", "A2") + hop(2, 1, 19_800, "A2", "A3") + hop(3, 2, 19_700, "A3", "A1")
    alerts = round_tripping(warehouse(entries, RING), P, "${amount} {length} {days}")
    assert sorted(alerts["account_id"].to_list()) == ["A1", "A2", "A3"]


def test_round_tripping_ignores_a_chain_that_does_not_close_or_changes_size() -> None:
    chain = hop(1, 0, 20_000, "A1", "A2") + hop(2, 1, 19_800, "A2", "A3")
    assert round_tripping(warehouse(chain, RING), P, "{amount}{length}{days}").is_empty()
    shrinking = hop(1, 0, 20_000, "A1", "A2") + hop(2, 1, 12_000, "A2", "A3") + hop(3, 2, 11_000, "A3", "A1")
    assert round_tripping(warehouse(shrinking, RING), P, "{amount}{length}{days}").is_empty()


def test_only_complete_episodes_count_toward_recall() -> None:
    entries = (
        hop(1, 0, 20_000, "A1", "A2", ref=7)
        + hop(2, 1, 19_800, "A2", "A3", ref=7)
        + hop(3, 2, 19_700, "A3", "A1", ref=7)
        + hop(4, 30, 20_000, "A1", "A2", ref=8)
    )
    con = warehouse(entries, RING)
    rows = []
    for episode, days in ((7, 0), (8, 30)):
        for account in ("A1", "A2", "A3"):
            rows.append(
                {
                    "episode_id": episode,
                    "typology": "round_tripping",
                    "start_at": T0 + timedelta(days=days),
                    "end_at": T0 + timedelta(days=days + 3),
                    "n_entries": 6,
                    "amount": 20_000.0,
                    "ring_id": 0,
                    "customer_id": f"C{account}",
                    "account_id": account,
                }
            )
    truth = posted_truth(con, pl.DataFrame(rows))
    assert truth.filter(pl.col("episode_id") == 7)["complete"].all()
    assert not truth.filter(pl.col("episode_id") == 8)["complete"].any()
    alerts = round_tripping(con, P, "{amount}{length}{days}").with_row_index("alert_id", offset=1)
    table = scorecard(label_alerts(alerts, truth), truth, transactions=100_000)
    row = table.row(0, named=True)
    assert (row["episodes"], row["episodes_found"], row["partial_episodes"], row["recall"]) == (1, 1, 1, 1.0)


def test_evaluation_refuses_nothing() -> None:
    empty = pl.DataFrame(
        schema={
            "alert_id": pl.UInt32,
            "rule": pl.Utf8,
            "account_id": pl.Utf8,
            "start_at": pl.Datetime("us"),
            "end_at": pl.Datetime("us"),
        }
    )
    with pytest.raises(ValueError, match="no alerts"):
        label_alerts(empty, pl.DataFrame())
    with pytest.raises(ValueError, match="no transactions"):
        scorecard(empty, pl.DataFrame({"typology": ["mule"], "episode_id": [1], "complete": [True]}), 0)


def test_rules_file_has_a_statement_for_every_rule() -> None:
    con = warehouse([cash(1, 0, 9_000), cash(2, 2, 8_500), cash(3, 5, 9_900)])
    alerts = run_rules(con, P, ROOT / "rules")
    assert alerts["statement"][0].startswith("3 cash deposits between $8,000 and $10,000")


def test_communities_are_the_same_on_every_run() -> None:
    g = nx.karate_club_graph()
    nx.set_edge_attributes(g, 1.0, "amount")
    g = nx.relabel_nodes(g, {n: f"A{n}" for n in g.nodes})
    assert communities(g, seed=5) == communities(g, seed=5)
