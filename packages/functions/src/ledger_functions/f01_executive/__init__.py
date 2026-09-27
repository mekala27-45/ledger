"""Function 1: the bank at a glance, benchmarked to real peers.

Question: how is Harborline doing this quarter, and how does that compare with real
banks of its size in its region? The figures come from the metric layer, which is
built from the general ledger, which reconciles to the cent (function 11). The peers
are real FDIC insured institutions from the FDIC's own Call Report data; Harborline
is fictional, and every chart that puts them side by side says so.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Scalar

from ledger_functions.base import Context, FunctionSpec

PEER_ASSETS_THOUSANDS = (500_000, 2_500_000)
PEER_QUARTER = "2026Q2"

# Harborline metric, FDIC field, label, format, whether higher is better.
POSITIVE_ONLY = {"nim", "efficiency_ratio", "capital_ratio", "loans_to_deposits"}

RATIOS = (
    ("nim", "nim_pct", "Net interest margin", "pct2", True),
    ("efficiency_ratio", "efficiency_ratio_pct", "Efficiency ratio", "pct1", False),
    ("roa", "roa_pct", "Return on assets", "pct2", True),
    ("roe", "roe_pct", "Return on equity", "pct1", True),
    ("npl_ratio", "noncurrent_loans_pct", "Nonperforming loans", "pct2", False),
    ("allowance_to_loans", "allowance_to_loans_pct", "Allowance to loans", "pct2", True),
    ("capital_ratio", "total_risk_based_capital_pct", "Capital ratio (simplified)", "pct1", True),
    ("loans_to_deposits", "loans_to_deposits", "Loans to deposits", "pct1", True),
)


def run(ctx: Context) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "Harborline Bank general ledger",
        "source": "metrics/bank.yaml",
    }
    quarter = pl.read_parquet(ctx.paths.results / "metrics" / "bank_quarter.parquet")
    monthly = pl.read_parquet(ctx.paths.results / "metrics" / "bank_month.parquet").rename(
        {"period": "month"}
    )
    window = pl.read_parquet(ctx.paths.results / "metrics" / "bank_window.parquet").row(0, named=True)
    latest = quarter.filter(pl.col("period") == PEER_QUARTER).row(0, named=True)
    prior = quarter.filter(pl.col("period") == "2026Q1").row(0, named=True)
    last_month = monthly.sort("month").row(-1, named=True)

    for key, fmt in (
        ("total_assets", "usdm"),
        ("total_deposits", "usdm"),
        ("total_loans", "usdm"),
        ("total_equity", "usdm"),
        ("allowance", "usdm"),
        ("nonperforming_loans", "usdm"),
    ):
        m.put(f"f01.{key}", last_month[key], fmt, **gen)
    trailing = monthly.sort("month").tail(12)
    m.put("f01.net_income_ttm", float(trailing["net_income"].sum()), "usdm", **gen)
    m.put("f01.net_interest_income_ttm", float(trailing["net_interest_income"].sum()), "usdm", **gen)
    m.put("f01.net_income_window", window["net_income"], "usdm", **gen)
    m.put("f01.as_of_month", last_month["month"], "text", **gen)
    for key, _, _label, fmt, _ in RATIOS:
        m.put(f"f01.{key}_q", latest[key], fmt, **gen)
        m.put(f"f01.{key}_prior_q", prior[key], fmt, **gen)
        m.put(f"f01.{key}_change_bps", (latest[key] - prior[key]) * 10_000, "int", **gen)

    # Each ratio's monthly trend with a normal range: the trailing twelve month mean plus or minus two standard deviations.
    trend = monthly.select(["month"] + [r[0] for r in RATIOS]).sort("month")
    for key, *_ in RATIOS:
        mean = trend[key].rolling_mean(12, min_samples=6)
        std = trend[key].rolling_std(12, min_samples=6)
        trend = trend.with_columns(
            (mean - 2 * std).alias(f"{key}_low"), (mean + 2 * std).alias(f"{key}_high")
        )
    ctx.save("ratios_monthly", trend)
    m.put_figure(
        "f01.fig_ratios",
        "The ratios every bank reports, monthly",
        _ratio_callout(latest, prior),
        data="f01/ratios_monthly.parquet",
        **gen,
    )

    # Real peers: FDIC insured institutions of Harborline's size in its seven state region.
    fdic = ctx.sql(
        """
        select cert, name, state, quarter, total_assets_thousands, nim_pct, efficiency_ratio_pct, roa_pct, roe_pct,
            noncurrent_loans_pct, allowance_to_loans_pct, total_risk_based_capital_pct, loans_to_deposits
        from marts.mart_fdic_peer_quarter
        where quarter = ? and total_assets_thousands between ? and ?
        """,
        [PEER_QUARTER, *PEER_ASSETS_THOUSANDS],
    )
    real: dict[str, Any] = {
        "backend": "real:fdic",
        "population": f"FDIC insured institutions, $0.5 to $2.5 billion in assets, CT DE MA MD NJ NY PA, {PEER_QUARTER}",
        "source": "FDIC BankFind financials",
    }
    m.put("f01.peer_count", fdic.height, "int", **real)
    m.put("f01.peer_quarter", PEER_QUARTER, "text", **real)
    rows: list[list[Scalar]] = []
    strips = []
    for key, field, label, fmt, higher_better in RATIOS:
        values = fdic[field].drop_nulls().cast(pl.Float64).to_numpy()
        values = values / 100.0 if field.endswith("_pct") else values
        if key in POSITIVE_ONLY:
            # A zero here is a bank that did not report the item, not a bank with no margin or capital.
            values = values[values > 0]
        ours = float(latest[key])
        pct = float((values < ours).mean()) if values.size else float("nan")
        q = np.quantile(values, [0.1, 0.25, 0.5, 0.75, 0.9]) if values.size else [np.nan] * 5
        rows.append(
            [label, ours, float(q[0]), float(q[2]), float(q[4]), pct, "higher" if higher_better else "lower"]
        )
        strips.append(pl.DataFrame({"ratio": label, "value": values, "fmt": fmt}))
        m.put(f"f01.peer_{key}_median", float(q[2]), fmt, **real)
        m.put(f"f01.peer_{key}_percentile", pct, "pct0", **real)
    ctx.save("peer_strips", pl.concat(strips))
    m.put_table(
        "f01.peer_table",
        [
            "Ratio",
            "Harborline (fictional)",
            "Peer 10th",
            "Peer median",
            "Peer 90th",
            "Share of peers below",
            "Better when",
        ],
        ["text", "pct2", "pct2", "pct2", "pct2", "pct0", "text"],
        rows,
        **real,
    )
    nim_pct = next(float(r[5]) for r in rows if r[0] == "Net interest margin" and isinstance(r[5], float))
    mix = ctx.sql(
        "select sum(loans_card) + sum(loans_installment) as consumer, sum(total_loans) as total "
        "from marts.mart_bank_month where month = ?",
        [last_month["month"]],
    ).row(0, named=True)
    consumer_share = float(mix["consumer"] / mix["total"])
    m.put("f01.consumer_loan_share", consumer_share, "pct0", **gen)
    m.put_figure(
        "f01.fig_peers",
        "Harborline against real peers",
        f"Harborline's net interest margin sits above {format_value(nim_pct, 'pct0')} of the "
        f"{fdic.height} real peers: {format_value(consumer_share, 'pct0')} of its loans are card and consumer "
        f"installment lending at double digit rates, where most community banks lend mortgages and business "
        f"loans. Its efficiency ratio and returns follow from that margin. The comparison is illustrative: the "
        f"peers are real FDIC insured banks and Harborline is not.",
        data="f01/peer_strips.parquet",
        **real,
    )

    insights = rules_engine(monthly, quarter, ctx)
    m.put_table(
        "f01.insights",
        ["Rank", "Insight", "Materiality"],
        ["int", "text", "usd0"],
        [[i + 1, text, size] for i, (text, size) in enumerate(insights)],
        **gen,
    )


def _ratio_callout(latest: dict[str, float], prior: dict[str, float]) -> str:
    nim_move = (latest["nim"] - prior["nim"]) * 10_000
    npl_move = (latest["npl_ratio"] - prior["npl_ratio"]) * 10_000
    return (
        f"Net interest margin was {format_value(latest['nim'], 'pct2')} in {PEER_QUARTER}, "
        f"{'up' if nim_move >= 0 else 'down'} {abs(nim_move):.0f} basis points on the quarter, and nonperforming "
        f"loans {'rose' if npl_move > 0 else 'fell'} {abs(npl_move):.0f} basis points to "
        f"{format_value(latest['npl_ratio'], 'pct2')}. The shaded band is each ratio's trailing twelve month mean "
        f"plus or minus two standard deviations."
    )


def rules_engine(monthly: pl.DataFrame, quarter: pl.DataFrame, ctx: Context) -> list[tuple[str, float]]:
    """Largest movers, anomalies and forecast against actual, ranked by dollar materiality."""
    found: list[tuple[str, float]] = []
    q = quarter.filter(pl.col("months") == 3).sort("first_month")
    if q.height >= 2:
        a, b = q.row(-2, named=True), q.row(-1, named=True)
        for key, label in (
            ("total_loans", "Gross loans"),
            ("total_deposits", "Deposits"),
            ("net_income", "Net income"),
            ("provision", "Provision expense"),
            ("noninterest_expense", "Noninterest expense"),
        ):
            change = float(b[key] - a[key])
            verb = "rose" if change >= 0 else "fell"
            found.append(
                (
                    f"{label} {verb} {format_value(abs(change), 'usdm')} from {a['period']} to {b['period']} "
                    f"({format_value(change / a[key] if a[key] else 0.0, 'spct1')}).",
                    abs(change),
                )
            )
    products = ctx.sql(
        "select product, month, balance from marts.mart_portfolio_monthly where month in ('2026-05', '2026-08')"
    )
    for product in products["product"].unique().sort().to_list():
        p = products.filter(pl.col("product") == product).sort("month")
        if p.height == 2:
            change = float(p["balance"][1] - p["balance"][0])
            verb = "rose" if change >= 0 else "fell"
            found.append(
                (
                    f"{product.capitalize()} balances {verb} {format_value(abs(change), 'usdm')} over the "
                    f"last quarter, to {format_value(float(p['balance'][1]), 'usdm')}.",
                    abs(change),
                )
            )
    # Anomalies: a month's net income more than two standard deviations from its trailing year.
    ni = (
        monthly.sort("month")
        .with_columns(
            mean=pl.col("net_income").rolling_mean(12, min_samples=6).shift(1),
            std=pl.col("net_income").rolling_std(12, min_samples=6).shift(1),
        )
        .drop_nulls(["mean", "std"])
    )
    for row in (
        ni.filter(((pl.col("net_income") - pl.col("mean")) / pl.col("std")).abs() > 2)
        .tail(3)
        .iter_rows(named=True)
    ):
        found.append(
            (
                f"Net income in {row['month']} was {format_value(row['net_income'], 'usdm')} against a trailing "
                f"average of {format_value(row['mean'], 'usdm')}, outside two standard deviations.",
                abs(float(row["net_income"] - row["mean"])),
            )
        )
    # Forecast against actual: a seasonal naive forecast of the last month's net interest income.
    series = monthly.sort("month")["net_interest_income"].to_list()
    if len(series) >= 13:
        forecast, actual = series[-13], series[-1]
        found.append(
            (
                f"Net interest income in the last month was {format_value(actual, 'usdm')} against a "
                f"same month last year forecast of {format_value(forecast, 'usdm')}.",
                abs(actual - forecast),
            )
        )
    found.sort(key=lambda x: -x[1])
    return found[:8]


SPEC = FunctionSpec(
    code="f01",
    slug="glance",
    title="The bank at a glance",
    question="How is the bank doing this quarter, and how does that compare with real banks of its size?",
    run=run,
)
