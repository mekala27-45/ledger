"""The transfer network: who pays whom inside the bank, in communities an investigator can read.

Accounts are nodes and transfers between different customers' accounts are edges,
weighted by the money that moved. Communities come from the Louvain method with a
fixed seed. Per community: the rule alerts on its accounts, the money inside it, and
the share of its accounts already alerted. The investigator's view is a small graph
around the alerted communities, with each alerted account's outside counterparties
for the alert window as leaves, so a mule's fan in is visible as a star.
"""

from __future__ import annotations

from typing import Any

import duckdb
import networkx as nx
import polars as pl


def internal_edges(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Money between different customers' Harborline accounts, summed per ordered pair."""
    return con.execute(
        """
        select t.source_party as src, t.target_party as dst, sum(t.amount)::double as amount, count(*) as transfers
        from marts.mart_transfer_edges t
        join marts.dim_deposit_account s on s.account_id = t.source_party
        join marts.dim_deposit_account d on d.account_id = t.target_party
        where t.txn_type = 'INTERNAL_TRANSFER' and s.customer_id <> d.customer_id
        group by 1, 2
        order by 1, 2
        """
    ).pl()


def build_graph(edges: pl.DataFrame) -> nx.Graph:
    """The undirected transfer graph. Louvain's result depends on the order nodes and edges
    arrive in as well as on its seed, so the edges are added in a fixed order."""
    g = nx.Graph()
    for src, dst, amount, transfers in edges.sort("src", "dst").iter_rows():
        if g.has_edge(src, dst):
            g.edges[src, dst]["amount"] += amount
            g.edges[src, dst]["transfers"] += transfers
        else:
            g.add_edge(src, dst, amount=amount, transfers=transfers)
    return g


def communities(g: nx.Graph, seed: int) -> dict[str, int]:
    """Louvain communities, numbered from the largest."""
    found = nx.community.louvain_communities(g, weight="amount", seed=seed)
    ordered = sorted(found, key=lambda c: (-len(c), min(c)))
    return {node: i for i, members in enumerate(ordered) for node in members}


def community_table(
    g: nx.Graph, membership: dict[str, int], alerts: pl.DataFrame, truth: pl.DataFrame
) -> pl.DataFrame:
    """Per community: accounts, money inside, alerts, share alerted, and injected typology members."""
    frame = pl.DataFrame({"account_id": list(membership), "community": list(membership.values())})
    alerted = alerts.group_by("account_id").agg(
        pl.len().alias("alerts"), pl.col("rule").unique().alias("rules")
    )
    typed = truth.group_by("account_id").agg(pl.col("typology").first().alias("typology"))
    frame = frame.join(alerted, on="account_id", how="left").join(typed, on="account_id", how="left")
    flow: dict[int, float] = {}
    for a, b, data in g.edges(data=True):
        if membership[a] == membership[b]:
            flow[membership[a]] = flow.get(membership[a], 0.0) + float(data["amount"])
    return (
        frame.group_by("community")
        .agg(
            pl.len().alias("accounts"),
            pl.col("alerts").fill_null(0).sum().alias("alerts"),
            pl.col("alerts").is_not_null().mean().alias("share_alerted"),
            pl.col("typology").is_not_null().sum().alias("injected_accounts"),
            pl.col("rules").explode().drop_nulls().unique().sort().str.join(", ").alias("rules_fired"),
        )
        .with_columns(
            internal_flow=pl.col("community").replace_strict(flow, default=0.0, return_dtype=pl.Float64)
        )
        .sort("community")
    )


def investigator_view(
    g: nx.Graph,
    membership: dict[str, int],
    table: pl.DataFrame,
    alerts: pl.DataFrame,
    truth: pl.DataFrame,
    leaves: pl.DataFrame,
    max_communities: int = 14,
    max_stars: int = 5,
) -> dict[str, Any]:
    """Nodes and links for the page: the alerted communities, with outside counterparties as leaves."""
    chosen = (
        table.filter(pl.col("alerts") > 0)
        .sort(["injected_accounts", "share_alerted", "alerts"], descending=True)
        .head(max_communities)["community"]
        .to_list()
    )
    rank = {c: i for i, c in enumerate(chosen)}
    keep = [n for n, c in membership.items() if c in rank]
    alerted = dict(
        alerts.group_by("account_id").agg(pl.col("rule").unique().sort().str.join(", ")).iter_rows()
    )
    rings = dict(
        truth.filter(pl.col("ring_id") >= 0).group_by("account_id").agg(pl.col("ring_id").first()).iter_rows()
    )
    typologies = dict(truth.group_by("account_id").agg(pl.col("typology").first()).iter_rows())
    nodes = [
        {
            "id": n,
            "community": rank[membership[n]],
            "alerted": alerted.get(n, ""),
            "injected": typologies.get(n, ""),
            "ring": rings.get(n),
            "outside": False,
        }
        for n in sorted(keep)
    ]
    kept = set(keep)
    # A subgraph of a few nodes iterates them from the set it was given, and a set of strings
    # comes out in a different order in every Python process, so the links are put in order
    # here, each internal one written from the lower account id to the higher.
    links = sorted(
        (
            {
                "source": min(a, b),
                "target": max(a, b),
                "amount": round(float(d["amount"]), 2),
                "transfers": int(d["transfers"]),
            }
            for a, b, d in g.subgraph(kept).edges(data=True)
        ),
        key=lambda link: (link["source"], link["target"]),
    )
    # A few mule accounts as stars of their own: their senders are outside the bank, so the
    # internal graph alone would never show the fan in.
    mules = [
        a
        for a in alerts.filter(pl.col("rule") == "mule")
        .sort("end_at", descending=True)["account_id"]
        .unique(maintain_order=True)
        .to_list()
        if a not in set(keep)
    ][:max_stars]
    for i, account in enumerate(mules):
        membership = {**membership, account: -1 - i}
        rank[-1 - i] = len(chosen) + i
        nodes.append(
            {
                "id": account,
                "community": rank[-1 - i],
                "alerted": alerted.get(account, ""),
                "injected": typologies.get(account, ""),
                "ring": None,
                "outside": False,
            }
        )
    keep = keep + mules
    # Outside counterparties for the alerted accounts shown, during their alert windows.
    shown_alerted = [n for n in keep if n in alerted]
    extra = leaves.filter(pl.col("account_id").is_in(shown_alerted))
    seen: set[str] = set()
    for account, party, amount in extra.select("account_id", "party", "amount").iter_rows():
        if party not in seen:
            nodes.append(
                {
                    "id": party,
                    "community": rank[membership[account]],
                    "alerted": "",
                    "injected": "",
                    "ring": None,
                    "outside": True,
                }
            )
            seen.add(party)
        links.append({"source": party, "target": account, "amount": round(float(amount), 2), "transfers": 1})
    return {"nodes": nodes, "links": links, "communities": chosen}


def alert_counterparties(con: duckdb.DuckDBPyConnection, alerts: pl.DataFrame) -> pl.DataFrame:
    """Outside parties that paid into or out of an alerted account during its alert window."""
    keys = alerts.filter(pl.col("rule").is_in(["mule", "rapid_movement"])).select(
        "account_id", "start_at", "end_at"
    )
    if keys.is_empty():
        return pl.DataFrame(schema={"account_id": pl.Utf8, "party": pl.Utf8, "amount": pl.Float64})
    con.register("alert_windows", keys.to_arrow())
    try:
        return con.execute(
            """
            select distinct e.account_id, e.counterparty_id as party, abs(e.amount)::double as amount
            from alert_windows w
            join marts.fct_deposit_entry e
                on e.account_id = w.account_id and e.posted_at between w.start_at and w.end_at
            where e.counterparty_id is not null and e.txn_type in ('P2P_IN', 'WIRE_IN', 'WIRE_OUT', 'P2P_OUT')
            order by 1, 2, 3
            """
        ).pl()
    finally:
        con.unregister("alert_windows")
