"""Function 6: deposits and customers.

Question: where are the deposits, how concentrated are they, how much of a rate move
reaches the customer, and whom should the bank call before they leave?

Method: balances, openings and closings by product from the deposit marts; the share
of deposits held by the top one percent of customers, a liquidity risk figure; product
holding and cross holding; deposit betas recovered two ways, from the rate sheet (the
offered rate, checked against the generator's known parameters) and from interest
actually credited (the paid rate, which lags for time deposits because a CD reprices
only when it matures); and the attrition model's retention list.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest, Scalar

from ledger_functions.base import Context, FunctionSpec

PRODUCTS = ("checking", "savings", "time")
PRODUCT_NAMES = {"checking": "Checking", "savings": "Savings", "time": "Time deposits"}
BETA_TOLERANCE = 0.02
CYCLE_START = "2024-08"


def offered_beta(rates: pl.DataFrame, product: str, floor: float | None) -> float:
    """The slope of the offered rate on the policy rate, over months the floor does not bind."""
    frame = rates if floor is None else rates.filter(pl.col(f"{product}_rate") > floor + 1e-9)
    x = frame["policy_rate"].to_numpy()
    y = frame[f"{product}_rate"].to_numpy()
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def run(ctx: Context) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "Harborline deposit accounts, September 2023 to August 2026",
        "source": "marts.mart_deposits_monthly",
    }
    as_of = ctx.config.calendar.as_of.strftime("%Y-%m")

    # Balances, openings and closings by product.
    monthly = ctx.sql(
        """
        select product, month, accounts, balance::double as balance, opened, closed
        from marts.mart_deposits_monthly order by month, product
        """
    )
    ctx.save("deposits_monthly", monthly)
    now = monthly.filter(pl.col("month") == as_of)
    total = float(now["balance"].sum())
    first = monthly.filter(pl.col("month") == monthly["month"].min())
    m.put("f06.deposits", total, "usdm", **gen)
    m.put("f06.deposits_start", float(first["balance"].sum()), "usdm", **gen)
    m.put("f06.growth", total / float(first["balance"].sum()) - 1, "spct1", **gen)
    for product in PRODUCTS:
        row = now.filter(pl.col("product") == product)
        m.put(f"f06.{product}_balance", float(row["balance"].sum()), "usdm", **gen)
        m.put(f"f06.{product}_share", float(row["balance"].sum()) / total, "pct1", **gen)
        m.put(f"f06.{product}_accounts", int(row["accounts"].sum()), "int", **gen)
    m.put_figure(
        "f06.fig_balances",
        "Deposits by product",
        f"Deposits stood at {format_value(total, 'usdm')} in {as_of}, "
        f"{format_value(total / float(first['balance'].sum()) - 1, 'spct1')} since the first month. "
        f"Checking is {format_value(float(now.filter(pl.col('product') == 'checking')['balance'].sum()) / total, 'pct1')} "
        "of the total: the cheapest money the bank has, and the first to leave when a customer does.",
        data="f06/deposits_monthly.parquet",
        **gen,
    )
    checking = monthly.filter(pl.col("product") == "checking")
    m.put("f06.checking_opened", int(checking["opened"].sum()), "int", **gen)
    m.put("f06.checking_closed", int(checking["closed"].sum()), "int", **gen)
    m.put_figure(
        "f06.fig_flows",
        "Checking accounts opened and closed each month",
        f"{format_value(int(checking['opened'].sum()), 'int')} checking accounts opened and "
        f"{format_value(int(checking['closed'].sum()), 'int')} closed over the three years. Closures are the "
        "attrition model's outcome; the retention list below is its use.",
        data="f06/deposits_monthly.parquet",
        **gen,
    )

    # Concentration: the share of deposits held by the largest depositors.
    holders = ctx.sql(
        f"""
        select customer_id, greatest(checking_balance, 0)::double + greatest(other_balance, 0)::double as balance
        from marts.mart_customer_month where month = '{as_of}'
        """
    ).sort("balance", descending=True)
    balances = holders["balance"].to_numpy()
    shares = {}
    for pct in (0.01, 0.05, 0.10):
        k = max(1, int(round(pct * balances.size)))
        shares[pct] = float(balances[:k].sum() / balances.sum())
    m.put("f06.top1_share", shares[0.01], "pct1", **gen)
    m.put("f06.top10_share", shares[0.10], "pct1", **gen)
    m.put("f06.depositors", int(balances.size), "int", **gen)
    m.put_table(
        "f06.concentration",
        ["Largest depositors", "Customers", "Share of deposits"],
        ["text", "int", "pct1"],
        [
            [label, max(1, int(round(pct * balances.size))), shares[pct]]
            for label, pct in (("Top 1%", 0.01), ("Top 5%", 0.05), ("Top 10%", 0.10))
        ],
        **gen,
    )

    # Product holding and cross holding, as of the last month.
    held = ctx.sql(
        """
        select count(*) as customers,
            avg((checking_accounts > 0)::int) as checking,
            avg((savings_accounts > 0)::int) as savings,
            avg((time_accounts > 0)::int) as time_deposit,
            avg((card_accounts + installment_loans + mortgages > 0)::int) as credit,
            avg((checking_accounts > 0 and savings_accounts > 0)::int) as checking_and_savings,
            avg((checking_accounts > 0 and card_accounts + installment_loans + mortgages > 0)::int) as deposit_and_credit,
            avg(product_types_held)::double as products
        from marts.dim_customer
        """
    ).row(0, named=True)
    m.put("f06.products_per_customer", held["products"], "float2", **gen)
    m.put("f06.cross_share", held["deposit_and_credit"], "pct1", **gen)
    m.put_table(
        "f06.holding",
        ["Holding", "Share of customers"],
        ["text", "pct1"],
        [
            ["Checking", held["checking"]],
            ["Savings", held["savings"]],
            ["A time deposit", held["time_deposit"]],
            ["Any credit product", held["credit"]],
            ["Checking and savings", held["checking_and_savings"]],
            ["Checking and any credit product", held["deposit_and_credit"]],
        ],
        **gen,
    )

    # Deposit betas: offered, against the generator's known parameters, and paid.
    rates = ctx.sql(
        "select month, policy_rate, checking_rate, savings_rate, time_rate from staging.stg_deposit_rates order by month"
    )
    truth = json.loads((ctx.paths.raw / "truth" / "truth_parameters.json").read_text())["betas"]
    floors = {"checking": truth["checking_floor"], "savings": truth["savings_floor"], "time": None}
    paid = ctx.sql(
        """
        with i as (
            select product, month, sum(amount)::double as interest
            from marts.fct_deposit_entry where txn_type = 'INTEREST_CREDIT' group by 1, 2
        ),
        b as (
            select a.product, b.month, sum(b.opening_balance + b.closing_balance)::double / 2 as average_balance
            from staging.stg_deposit_balances b join marts.dim_deposit_account a using (account_id) group by 1, 2
        )
        select b.month, b.product, coalesce(i.interest, 0) / b.average_balance * 1200 as paid_rate
        from b left join i using (product, month) order by 1, 2
        """
    )
    wide = paid.pivot(on="product", index="month", values="paid_rate").join(rates, on="month").sort("month")
    ctx.save("rates", wide)
    start = wide.filter(pl.col("month") == CYCLE_START).row(0, named=True)
    end = wide.filter(pl.col("month") == as_of).row(0, named=True)
    one_year = wide.filter(pl.col("month") == "2025-08").row(0, named=True)
    move = end["policy_rate"] - start["policy_rate"]
    rows: list[list[Scalar]] = []
    betas: dict[str, tuple[float, float, float]] = {}  # product: (offered, paid first year, paid cycle)
    recovered = 0
    for product in PRODUCTS:
        b = offered_beta(rates, product, floors[product])
        ok = abs(b - truth[product]) <= BETA_TOLERANCE
        recovered += int(ok)
        paid_cycle = (end[product] - start[product]) / move
        paid_year = (one_year[product] - start[product]) / (one_year["policy_rate"] - start["policy_rate"])
        m.put(f"f06.beta_{product}", b, "float2", **gen)
        m.put(f"f06.paid_beta_{product}", paid_cycle, "float2", **gen)
        m.put(f"f06.paid_beta_year_{product}", paid_year, "float2", **gen)
        rows.append([PRODUCT_NAMES[product], truth[product], b, "yes" if ok else "no", paid_year, paid_cycle])
        betas[product] = (b, paid_year, paid_cycle)
    m.put("f06.betas_recovered", recovered, "int", **gen)
    m.put("f06.beta_products", len(PRODUCTS), "int", **gen)
    m.put("f06.beta_tolerance", BETA_TOLERANCE, "float2", **gen)
    m.put("f06.policy_move", move, "float2", **gen)
    m.put("f06.policy_cut", abs(move), "float2", **gen)
    m.put_table(
        "f06.betas",
        [
            "Product",
            "Generator's beta",
            "Recovered from the rate sheet",
            f"Within {BETA_TOLERANCE:g}",
            "Paid rate beta, first year of cuts",
            "Paid rate beta, whole cycle",
        ],
        ["text", "float2", "float2", "text", "float2", "float2"],
        rows,
        **gen,
    )
    m.put_figure(
        "f06.fig_rates",
        "The policy rate, and what each product pays",
        f"The policy rate fell {format_value(abs(move), 'float2')} points from {CYCLE_START} to {as_of}. Savings "
        f"passed on {format_value(betas['savings'][2], 'float2')} of it (its offered beta is "
        f"{format_value(betas['savings'][0], 'float2')}); time deposits passed on only "
        f"{format_value(betas['time'][1], 'float2')} in the first year, because a certificate reprices only when it "
        f"matures, and {format_value(betas['time'][2], 'float2')} by the end. Treasury's rate shocks use these betas.",
        data="f06/rates.parquet",
        **gen,
    )

    # The retention list.
    model = Manifest.load(ctx.paths.models_dir / "attrition" / "manifest.json")
    listed = pl.read_parquet(ctx.paths.models_dir / "attrition" / "retention_list.parquet")
    ctx.save("retention_list", listed)
    mk = "models.attrition"
    for key in (
        "list_size",
        "list_expected_balance",
        "list_balances",
        "portfolio_expected_balance",
        "customers_scored",
    ):
        entry = model.values[f"{mk}.{key}"]
        m.put(f"f06.{key}", entry.value, entry.fmt, **gen)
    m.put_table(
        "f06.retention_top",
        ["Customer", "Probability of leaving within a year", "Balances", "Expected balance at risk", "Why"],
        ["text", "pct1", "usd0", "usd0", "text"],
        listed.head(15).rows(),
        **gen,
    )
    m.put_figure(
        "f06.fig_retention",
        "The retention list: expected balance at risk",
        f"The {format_value(listed.height, 'int')} customers at the top of the list hold "
        f"{format_value(float(listed['balance_total'].sum()), 'usd0')} and carry "
        f"{format_value(float(listed['expected_balance_at_risk'].sum()), 'usd0')} of expected balance at risk, out of "
        f"{model.text(mk + '.portfolio_expected_balance')} across all {model.text(mk + '.customers_scored')} checking "
        "customers. The list is ordered by probability times balance, so a call goes to the relationship worth keeping.",
        data="f06/retention_list.parquet",
        **gen,
    )


SPEC = FunctionSpec(
    code="f06",
    slug="deposits",
    title="Deposits and customers",
    question="Where are the deposits, how concentrated are they, how much of a rate move reaches customers, and whom should the bank call before they leave?",
    run=run,
)
