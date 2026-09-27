"""Transaction monitoring rules, one per typology, over the deposit sub ledger.

Every rule reads the warehouse, fires on a window of one account's activity, and
returns alerts in one shape: the rule, the account, the window, the money involved,
a plain words statement, and the facts the triage model scores. Thresholds come
from config/ledger.yaml, where the generator's injected typologies read them too.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import networkx as nx
import polars as pl
import yaml

ALERT_COLUMNS = [
    "rule",
    "account_id",
    "customer_id",
    "start_at",
    "end_at",
    "amount",
    "entries",
    "counterparties",
    "branches",
    "statement",
]


@dataclass(frozen=True)
class AmlParams:
    reporting_threshold: float
    structuring_floor: float
    structuring_window_days: int
    rapid_movement_hours: int
    mule_fan_in_min_counterparties: int
    mule_window_days: int
    cycle_max_length: int
    cycle_window_days: int
    rapid_share: float = 0.8
    mule_out_share: float = 0.6
    cycle_floor: float = 5_000.0
    cycle_tolerance: float = 0.1


def load_statements(rules_dir: Path) -> dict[str, str]:
    data = yaml.safe_load((rules_dir / "aml_typologies.yaml").read_text(encoding="utf-8"))
    return {r["id"]: r["statement"] for r in data["rules"]}


def _money(x: float) -> str:
    return f"{x:,.0f}"


def structuring(con: duckdb.DuckDBPyConnection, p: AmlParams, statement: str) -> pl.DataFrame:
    """At least three cash deposits just under the threshold in a window, together above it."""
    deposits = con.execute(
        """
        select account_id, customer_id, posted_at, amount::double as amount, branch_id
        from marts.fct_deposit_entry
        where txn_type = 'CASH_DEPOSIT' and amount >= ? and amount < ?
        order by account_id, posted_at
        """,
        [p.structuring_floor, p.reporting_threshold],
    ).pl()
    if deposits.is_empty():
        return _empty()
    window = f"{p.structuring_window_days}d"
    rolled = (
        deposits.rolling(index_column="posted_at", period=window, group_by="account_id")
        .agg(
            pl.col("customer_id").first(),
            pl.len().alias("entries"),
            pl.col("amount").sum().alias("amount"),
            pl.col("branch_id").n_unique().alias("branches"),
            pl.col("posted_at").min().alias("start_at"),
        )
        .rename({"posted_at": "end_at"})
        .filter((pl.col("entries") >= 3) & (pl.col("amount") >= p.reporting_threshold))
    )
    # One alert per burst: keep the window that ends last before the next quiet gap.
    bursts = _collapse(rolled, p.structuring_window_days)
    return bursts.with_columns(
        rule=pl.lit("structuring"),
        counterparties=pl.lit(0, dtype=pl.UInt32),
        statement=pl.struct("entries", "amount").map_elements(
            lambda s: statement.format(
                count=s["entries"],
                floor=_money(p.structuring_floor),
                threshold=_money(p.reporting_threshold),
                days=p.structuring_window_days,
                total=_money(s["amount"]),
            ),
            return_dtype=pl.Utf8,
        ),
    ).select(ALERT_COLUMNS)


def rapid_movement(con: duckdb.DuckDBPyConnection, p: AmlParams, statement: str) -> pl.DataFrame:
    """A wire of at least the reporting threshold in, and most of it out again within hours."""
    moves = con.execute(
        """
        with inbound as (
            select account_id, customer_id, posted_at, amount::double as amount
            from marts.fct_deposit_entry
            where txn_type = 'WIRE_IN' and amount >= ?
        ),
        outbound as (
            select account_id, posted_at, -amount::double as amount, coalesce(counterparty_id, counterparty_account_id) as cp
            from marts.fct_deposit_entry
            where txn_type in ('WIRE_OUT', 'ACH_OUT', 'P2P_OUT') and amount < 0
        )
        select i.account_id, i.customer_id, i.posted_at as start_at, max(o.posted_at) as end_at,
            i.amount as inbound, sum(o.amount) as outbound, count(*) as entries, count(distinct o.cp) as counterparties
        from inbound i join outbound o
            on o.account_id = i.account_id
            and o.posted_at > i.posted_at
            and o.posted_at <= i.posted_at + to_hours(?)
        group by 1, 2, 3, 5
        having sum(o.amount) >= ? * i.amount
        order by 1, 3
        """,
        [p.reporting_threshold, p.rapid_movement_hours, p.rapid_share],
    ).pl()
    if moves.is_empty():
        return _empty()
    return moves.with_columns(
        rule=pl.lit("rapid_movement"),
        amount=pl.col("inbound"),
        entries=(pl.col("entries") + 1).cast(pl.UInt32),
        counterparties=pl.col("counterparties").cast(pl.UInt32),
        branches=pl.lit(0, dtype=pl.UInt32),
        statement=pl.struct("inbound", "outbound").map_elements(
            lambda s: statement.format(
                inbound=_money(s["inbound"]), outbound=_money(s["outbound"]), hours=p.rapid_movement_hours
            ),
            return_dtype=pl.Utf8,
        ),
    ).select(ALERT_COLUMNS)


def mule(con: duckdb.DuckDBPyConnection, p: AmlParams, statement: str) -> pl.DataFrame:
    """Many senders in a short window, then most of the money out in one transfer."""
    rows = con.execute(
        """
        with outbound as (
            select account_id, customer_id, posted_at, -amount::double as amount
            from marts.fct_deposit_entry
            where txn_type in ('WIRE_OUT', 'P2P_OUT', 'ACH_OUT') and amount < 0
        ),
        inbound as (
            select account_id, posted_at, amount::double as amount, counterparty_id
            from marts.fct_deposit_entry
            where txn_type = 'P2P_IN'
        )
        select o.account_id, o.customer_id, min(i.posted_at) as start_at, o.posted_at as end_at,
            o.amount as outbound, sum(i.amount) as inflow, count(*) as entries,
            count(distinct i.counterparty_id) as counterparties
        from outbound o join inbound i
            on i.account_id = o.account_id
            and i.posted_at < o.posted_at
            and i.posted_at >= o.posted_at - to_days(?)
        group by 1, 2, 4, 5
        having count(distinct i.counterparty_id) >= ? and o.amount >= ? * sum(i.amount)
        order by 1, 4
        """,
        [p.mule_window_days, p.mule_fan_in_min_counterparties, p.mule_out_share],
    ).pl()
    if rows.is_empty():
        return _empty()
    return rows.with_columns(
        rule=pl.lit("mule"),
        amount=pl.col("inflow"),
        entries=(pl.col("entries") + 1).cast(pl.UInt32),
        counterparties=pl.col("counterparties").cast(pl.UInt32),
        branches=pl.lit(0, dtype=pl.UInt32),
        statement=pl.struct("counterparties", "outbound").map_elements(
            lambda s: statement.format(
                senders=s["counterparties"], days=p.mule_window_days, outbound=_money(s["outbound"])
            ),
            return_dtype=pl.Utf8,
        ),
    ).select(ALERT_COLUMNS)


def round_tripping(con: duckdb.DuckDBPyConnection, p: AmlParams, statement: str) -> pl.DataFrame:
    """Money that leaves an account, passes through others, and comes home at about the same size."""
    edges = con.execute(
        """
        select t.source_party as src, t.target_party as dst, t.posted_at, t.amount::double as amount,
            s.customer_id as src_customer
        from marts.mart_transfer_edges t
        join marts.dim_deposit_account s on s.account_id = t.source_party
        join marts.dim_deposit_account d on d.account_id = t.target_party
        where t.txn_type = 'INTERNAL_TRANSFER' and s.customer_id <> d.customer_id and t.amount >= ?
        order by t.posted_at
        """,
        [p.cycle_floor],
    ).pl()
    if edges.is_empty():
        return _empty()
    found: dict[tuple[str, ...], dict[str, object]] = {}
    span = pl.duration(days=p.cycle_window_days)
    starts = edges.select("posted_at").unique().sort("posted_at")["posted_at"].to_list()
    for start in starts:
        window = edges.filter((pl.col("posted_at") >= start) & (pl.col("posted_at") <= pl.lit(start) + span))
        if window.height < 2:
            continue
        g = nx.DiGraph()
        for r in window.iter_rows(named=True):
            g.add_edge(r["src"], r["dst"], amount=r["amount"], at=r["posted_at"], customer=r["src_customer"])
        for cycle in nx.simple_cycles(g, length_bound=p.cycle_max_length):
            if len(cycle) < 2:
                continue
            hops = [g.edges[cycle[i], cycle[(i + 1) % len(cycle)]] for i in range(len(cycle))]
            amounts = [float(h["amount"]) for h in hops]
            if max(amounts) > (1 + p.cycle_tolerance) * min(amounts):
                continue
            ring = tuple(sorted(cycle))
            times = [h["at"] for h in hops]
            first, last = min(times), max(times)
            # One alert per trip around the ring: overlapping windows find the same trip again.
            key = (*ring, str(first))
            if key not in found:
                found[key] = {
                    "accounts": list(ring),
                    "start_at": first,
                    "end_at": last,
                    "amount": max(amounts),
                    "length": len(cycle),
                    "customer": hops[0]["customer"],
                }
    if not found:
        return _empty()
    rows = []
    for r in found.values():
        ring = tuple(r["accounts"])  # type: ignore[arg-type]
        for account in ring:
            rows.append(
                {
                    "rule": "round_tripping",
                    "account_id": account,
                    "customer_id": None,
                    "start_at": r["start_at"],
                    "end_at": r["end_at"],
                    "amount": r["amount"],
                    "entries": r["length"],
                    "counterparties": int(r["length"]) - 1,  # type: ignore[call-overload]
                    "branches": 0,
                    "statement": statement.format(
                        amount=_money(float(r["amount"])),  # type: ignore[arg-type]
                        length=r["length"],
                        days=p.cycle_window_days,
                    ),
                    "ring": "|".join(ring),
                }
            )
    frame = pl.DataFrame(rows)
    customers = con.execute("select account_id, customer_id as cust from marts.dim_deposit_account").pl()
    frame = frame.join(customers, on="account_id", how="left").with_columns(customer_id=pl.col("cust"))
    return frame.with_columns(
        entries=pl.col("entries").cast(pl.UInt32),
        counterparties=pl.col("counterparties").cast(pl.UInt32),
        branches=pl.col("branches").cast(pl.UInt32),
    ).select([*ALERT_COLUMNS, "ring"])


def _collapse(rolled: pl.DataFrame, days: int) -> pl.DataFrame:
    """Overlapping windows of one account become one alert spanning the burst."""
    rolled = rolled.sort("account_id", "end_at")
    gap = pl.col("start_at") > pl.col("end_at").shift(1).over("account_id")
    burst = gap.fill_null(True).cast(pl.Int32).cum_sum().over("account_id")
    return (
        rolled.with_columns(burst=burst)
        .group_by("account_id", "burst")
        .agg(
            pl.col("customer_id").first(),
            pl.col("start_at").min(),
            pl.col("end_at").max(),
            pl.col("entries").max(),
            pl.col("amount").max(),
            pl.col("branches").max(),
        )
        .drop("burst")
        .with_columns(entries=pl.col("entries").cast(pl.UInt32), branches=pl.col("branches").cast(pl.UInt32))
        .sort("account_id", "start_at")
    )


def _empty() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule": pl.Utf8,
            "account_id": pl.Utf8,
            "customer_id": pl.Utf8,
            "start_at": pl.Datetime("us"),
            "end_at": pl.Datetime("us"),
            "amount": pl.Float64,
            "entries": pl.UInt32,
            "counterparties": pl.UInt32,
            "branches": pl.UInt32,
            "statement": pl.Utf8,
        }
    )


def run_rules(con: duckdb.DuckDBPyConnection, p: AmlParams, rules_dir: Path) -> pl.DataFrame:
    """Every rule's alerts in one frame, numbered in time order."""
    statements = load_statements(rules_dir)
    parts = [
        structuring(con, p, statements["structuring"]),
        rapid_movement(con, p, statements["rapid_movement"]),
        mule(con, p, statements["mule"]),
    ]
    trips = round_tripping(con, p, statements["round_tripping"])
    if "ring" not in trips.columns:
        trips = trips.with_columns(ring=pl.lit(None, dtype=pl.Utf8))
    frames = [x.with_columns(ring=pl.lit(None, dtype=pl.Utf8)) for x in parts] + [trips]
    alerts = pl.concat([f.select([*ALERT_COLUMNS, "ring"]) for f in frames], how="vertical_relaxed")
    return alerts.sort("end_at", "rule", "account_id").with_row_index("alert_id", offset=1)
