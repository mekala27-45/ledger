"""Function 5: financial crime.

Question: do the monitoring rules find the laundering typologies planted in the bank,
at an alert volume a compliance team could work, in an order that puts the real ones
first, and what does the transfer network show an investigator?

Method: four rules at the reporting threshold's boundary, graded against the
generator's injected truth (precision and recall by typology, alerts per hundred
thousand transactions); aml_triage as the queue's sort order; Louvain communities on
the transfers between customers, with the planted rings checked against them. Nothing
here is a suspicious activity finding and no report is filed anywhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest, Scalar
from ledger_crime.evaluate import posted_truth
from ledger_crime.network import (
    alert_counterparties,
    build_graph,
    communities,
    community_table,
    internal_edges,
    investigator_view,
)

from ledger_functions.base import Context, FunctionSpec

QUEUE_DAYS = 60
RULE_NAMES = {
    "structuring": "Structuring",
    "rapid_movement": "Rapid movement",
    "mule": "Mule fan in",
    "round_tripping": "Round tripping",
}


def run(ctx: Context) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "Harborline deposit accounts and their entries, September 2023 to August 2026",
        "source": "packages/crime",
    }
    folder = ctx.paths.models_dir / "aml_triage"
    triage = Manifest.load(folder / "manifest.json")
    alerts = pl.read_parquet(folder / "alerts_scored.parquet")
    card = pl.read_parquet(folder / "rule_scorecard.parquet")
    truth = posted_truth(ctx.con, pl.read_parquet(ctx.paths.raw / "truth" / "truth_typologies.parquet"))
    entries = int(ctx.sql("select count(*) as n from marts.fct_deposit_entry")["n"][0])

    ctx.save("rule_scorecard", card)
    m.put("f05.alerts", alerts.height, "int", **gen)
    m.put("f05.true_alerts", int(alerts["true_positive"].sum()), "int", **gen)
    m.put("f05.entries", entries, "int", **gen)
    m.put("f05.per_100k", alerts.height / entries * 100_000, "float1", **gen)
    m.put("f05.episodes", int(card["episodes"].sum()), "int", **gen)
    m.put("f05.episodes_found", int(card["episodes_found"].sum()), "int", **gen)
    m.put("f05.partial_episodes", int(card["partial_episodes"].sum()), "int", **gen)
    m.put("f05.recall", int(card["episodes_found"].sum()) / int(card["episodes"].sum()), "pct1", **gen)
    m.put("f05.precision", float(alerts["true_positive"].mean()), "pct1", **gen)  # type: ignore[arg-type]
    s = card.filter(pl.col("rule") == "structuring").row(0, named=True)
    m.put("f05.structuring_precision", s["precision"], "pct1", **gen)
    m.put("f05.structuring_recall", s["recall"], "pct1", **gen)
    m.put("f05.structuring_alerts", s["alerts"], "int", **gen)
    rows: list[list[Scalar]] = [
        [
            RULE_NAMES[r["rule"]],
            r["alerts"],
            r["precision"],
            r["episodes"],
            r["episodes_found"],
            r["recall"],
            r["partial_episodes"],
            r["per_100k"],
        ]
        for r in card.sort("alerts", descending=True).iter_rows(named=True)
    ]
    m.put_table(
        "f05.scorecard",
        [
            "Rule",
            "Alerts",
            "Precision",
            "Complete episodes",
            "Found",
            "Recall",
            "Posted in part",
            "Alerts per 100k entries",
        ],
        ["text", "int", "pct1", "int", "int", "pct1", "int", "float2"],
        rows,
        **gen,
    )
    m.put_figure(
        "f05.fig_scorecard",
        "What each rule finds, against the planted truth",
        f"The four rules fired {format_value(alerts.height, 'int')} alerts, "
        f"{format_value(alerts.height / entries * 100_000, 'float1')} per hundred thousand ledger entries, and found "
        f"{format_value(int(card['episodes_found'].sum()), 'int')} of {format_value(int(card['episodes'].sum()), 'int')} "
        f"complete planted episodes. Structuring is where the work is: {format_value(s['precision'], 'pct1')} of its "
        "alerts are real, because cash intensive businesses deposit just under the threshold for honest reasons. The "
        "other three rules fired no false alerts on this generator, which a real program should not expect.",
        data="f05/rule_scorecard.parquet",
        **gen,
    )

    # Alert volume by month and rule, the number a compliance team budgets by.
    monthly = (
        alerts.with_columns(month=pl.col("end_at").dt.strftime("%Y-%m"))
        .group_by("month", "rule")
        .agg(pl.len().alias("alerts"), pl.col("true_positive").sum().alias("true_alerts"))
        .sort("month", "rule")
    )
    ctx.save("alerts_monthly", monthly)
    busiest = (
        monthly.group_by("month")
        .agg(pl.col("alerts").sum())
        .sort("alerts", descending=True)
        .row(0, named=True)
    )
    m.put("f05.busiest_month", busiest["month"], "text", **gen)
    m.put("f05.busiest_month_alerts", busiest["alerts"], "int", **gen)
    months = monthly["month"].n_unique()
    m.put("f05.alerts_per_month", alerts.height / months, "float1", **gen)
    m.put_figure(
        "f05.fig_volume",
        "Alerts by month and rule",
        f"About {format_value(alerts.height / months, 'float1')} alerts a month, "
        f"{format_value(busiest['alerts'], 'int')} in the busiest, {busiest['month']}. That is the queue an investigator "
        "team is staffed for, and the triage order decides which of them is opened first.",
        data="f05/alerts_monthly.parquet",
        **gen,
    )

    # The queue as it stands on the as of date: the last two months' alerts, in triage order.
    last: datetime = alerts["end_at"].max()  # type: ignore[assignment]
    since = last - timedelta(days=QUEUE_DAYS)
    latest = f"{since:%Y-%m-%d} to {last:%Y-%m-%d}"
    queue = (
        alerts.filter(pl.col("end_at") > since)
        .sort("triage", descending=True)
        .with_row_index("position", offset=1)
        .select(
            "position",
            "alert_id",
            "rule",
            "account_id",
            "end_at",
            "amount",
            "triage",
            "statement",
            "true_positive",
        )
    )
    ctx.save("queue", queue)
    m.put("f05.queue_month", latest, "text", **gen)
    m.put("f05.queue_alerts", queue.height, "int", **gen)
    true_in_queue = int(queue["true_positive"].sum())
    m.put("f05.queue_true", true_in_queue, "int", **gen)
    falses = queue.filter(~pl.col("true_positive"))["position"].to_list()
    m.put("f05.queue_first_false", int(falses[0]) if falses else queue.height + 1, "int", **gen)
    m.put("f05.triage_auroc", triage.raw("models.aml_triage.test.auroc"), "float3", **gen)

    # The network.
    edges = internal_edges(ctx.con)
    g = build_graph(edges)
    membership = communities(g, seed=ctx.config.seed % 100_000)
    table = community_table(g, membership, alerts, truth)
    ctx.save("communities", table)
    net: dict[str, Any] = {**gen, "source": "Louvain communities over transfers between customers"}
    m.put("f05.accounts_in_network", g.number_of_nodes(), "int", **net)
    m.put("f05.links", g.number_of_edges(), "int", **net)
    m.put("f05.communities", len(set(membership.values())), "int", **net)
    alerted_comms = table.filter(pl.col("alerts") > 0)
    m.put("f05.alerted_communities", alerted_comms.height, "int", **net)
    # Planted rings: does each one sit inside a single community?
    ring_members = truth.filter(pl.col("ring_id") >= 0).select("ring_id", "account_id").unique()
    ring_members = ring_members.with_columns(
        community=pl.col("account_id").replace_strict(membership, default=None, return_dtype=pl.Int64)
    )
    rings = ring_members.group_by("ring_id").agg(
        pl.len().alias("members"),
        pl.col("community").n_unique().alias("communities"),
        pl.col("community").is_null().sum().alias("outside"),
    )
    whole = int(rings.filter((pl.col("communities") == 1) & (pl.col("outside") == 0)).height)
    m.put("f05.rings", rings.height, "int", **net)
    m.put("f05.rings_whole", whole, "int", **net)
    trips = alerts.filter(pl.col("rule") == "round_tripping")
    detected_rings = ring_members.filter(pl.col("account_id").is_in(trips["account_id"].to_list()))[
        "ring_id"
    ].n_unique()
    m.put("f05.rings_detected", detected_rings, "int", **net)
    rings_complete = truth.filter((pl.col("typology") == "round_tripping") & pl.col("complete"))[
        "ring_id"
    ].n_unique()
    m.put("f05.rings_with_complete_trip", rings_complete, "int", **net)
    components = nx_components(g)
    one_per_component = components == len(set(membership.values()))
    m.put("f05.components", components, "int", **net)
    top = alerted_comms.sort(["injected_accounts", "share_alerted"], descending=True).head(8)
    m.put_table(
        "f05.communities_table",
        [
            "Community",
            "Accounts",
            "Alerts",
            "Share alerted",
            "Planted accounts",
            "Rules fired",
            "Money inside",
        ],
        ["int", "int", "int", "pct1", "int", "text", "usd0"],
        [
            [
                r["community"],
                r["accounts"],
                r["alerts"],
                r["share_alerted"],
                r["injected_accounts"],
                r["rules_fired"] or "",
                r["internal_flow"],
            ]
            for r in top.iter_rows(named=True)
        ],
        **net,
    )
    m.put_figure(
        "f05.fig_network",
        "The investigator's view: alerted communities in the transfer network",
        f"The {format_value(g.number_of_nodes(), 'int')} accounts that pay other customers fall into "
        f"{format_value(components, 'int')} separate groups, mostly small circles of friends and family"
        + (
            ", and Louvain finds no finer structure inside any of them, so each group is one community. "
            if one_per_component
            else f", which Louvain splits into {format_value(len(set(membership.values())), 'int')} communities. "
        )
        + f"{format_value(whole, 'int')} of the {format_value(rings.height, 'int')} planted rings sit whole inside one "
        f"community, and the round tripping rule fired on members of {format_value(detected_rings, 'int')} of them"
        + (", every ring with a trip that posted in full. " if detected_rings == rings_complete else ". ")
        + "Mule accounts show as stars: many outside senders, one wire out.",
        data="f05/network.json",
        **net,
    )
    view = investigator_view(g, membership, table, alerts, truth, alert_counterparties(ctx.con, alerts))
    import json

    ctx.out.mkdir(parents=True, exist_ok=True)
    (ctx.out / "network.json").write_text(json.dumps(view, separators=(",", ":")), encoding="utf-8")
    m.put("f05.view_nodes", len(view["nodes"]), "int", **net)


def nx_components(g: Any) -> int:
    import networkx as nx

    return int(nx.number_connected_components(g))


SPEC = FunctionSpec(
    code="f05",
    slug="crime",
    title="Financial crime",
    question="Do the monitoring rules find the planted typologies at a workable volume, and in what order should "
    "an investigator open them?",
    run=run,
)
