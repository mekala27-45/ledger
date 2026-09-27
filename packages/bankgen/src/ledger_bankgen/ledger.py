"""The general ledger, posted from the sub ledgers.

Every deposit entry and every loan event becomes balanced postings (debits
positive, credits negative), each tied back to the sub ledger record that caused
it. Items with no customer behind them, such as securities income, operating
expense, the provision and liquidity moves, are journal entries with their own
register. The core system's reported month end balances are produced alongside,
and the stated ledger break is injected into those reported balances, which is
where a real break shows up: the balance the ledger reports no longer equals its
opening balance plus its postings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import Timeline

GL_CHART: list[tuple[str, str, str, str, str]] = [
    ("1000", "Cash and due from banks", "asset", "debit", "cash"),
    ("1100", "Investment securities", "asset", "debit", "securities"),
    ("1200", "Consumer installment loans", "asset", "debit", "loans_installment"),
    ("1210", "Credit card loans", "asset", "debit", "loans_card"),
    ("1220", "Residential mortgage loans", "asset", "debit", "loans_mortgage"),
    ("1290", "Allowance for credit losses", "contra_asset", "credit", "allowance"),
    ("2000", "Checking deposits", "liability", "credit", "deposits_checking"),
    ("2010", "Savings deposits", "liability", "credit", "deposits_savings"),
    ("2020", "Time deposits", "liability", "credit", "deposits_time"),
    ("2100", "Borrowings", "liability", "credit", "borrowings"),
    ("3000", "Common equity", "equity", "credit", "equity"),
    ("4000", "Interest income on loans", "income", "credit", "interest_income_loans"),
    ("4010", "Interest income on securities", "income", "credit", "interest_income_securities"),
    ("4100", "Service charges and fees", "income", "credit", "noninterest_income"),
    ("4200", "Card interchange income", "income", "credit", "noninterest_income"),
    ("5000", "Interest expense on deposits", "expense", "debit", "interest_expense_deposits"),
    ("5010", "Interest expense on borrowings", "expense", "debit", "interest_expense_borrowings"),
    ("5100", "Provision for credit losses", "expense", "debit", "provision"),
    ("5200", "Salaries and benefits", "expense", "debit", "noninterest_expense"),
    ("5210", "Occupancy and technology", "expense", "debit", "noninterest_expense"),
    ("5220", "Other noninterest expense", "expense", "debit", "noninterest_expense"),
    ("5300", "Income tax expense", "expense", "debit", "tax"),
]
DEPOSIT_GL = {"checking": "2000", "savings": "2010", "time": "2020"}
LOAN_GL = {"installment": "1200", "card": "1210", "mortgage": "1220"}
CASH_BALANCED = {
    "PAYROLL_IN",
    "BILL_PAY",
    "CARD_SPEND",
    "ATM_WITHDRAWAL",
    "CASH_DEPOSIT",
    "P2P_OUT",
    "P2P_IN",
    "WIRE_IN",
    "WIRE_OUT",
    "ACCOUNT_FUNDING",
    "CD_PAYOUT",
    "ACH_IN",
    "ACH_OUT",
}
LOSS_RATES = {"installment": 0.032, "card": 0.075, "mortgage": 0.0045}


@dataclass
class LedgerResult:
    chart: pl.DataFrame
    postings: pl.DataFrame
    journals: pl.DataFrame
    reported: pl.DataFrame
    truth_break: pl.DataFrame


def chart_frame() -> pl.DataFrame:
    return pl.DataFrame(
        GL_CHART,
        schema=["gl_account", "name", "account_type", "normal_balance", "statement_line"],
        orient="row",
    )


def _deposit_postings(
    entries: pl.DataFrame, accounts: pl.DataFrame, loan_links: pl.DataFrame
) -> pl.DataFrame:
    product = accounts.select("account_id", "product")
    e = entries.join(product, on="account_id", how="left").with_columns(
        gl_account=pl.col("product").replace_strict(DEPOSIT_GL, default=None)
    )
    legs = e.select(
        "transaction_id",
        pl.lit("deposit_entry").alias("source_type"),
        pl.col("entry_id").alias("source_id"),
        "gl_account",
        (-pl.col("amount")).alias("amount"),
        "posted_at",
        "month",
    )
    single = e.filter(pl.col("txn_type") != "INTERNAL_TRANSFER")
    balancing_gl = (
        pl.when(pl.col("txn_type").is_in(list(CASH_BALANCED)))
        .then(pl.lit("1000"))
        .when(pl.col("txn_type").is_in(["FEE_MAINTENANCE", "FEE_OVERDRAFT"]))
        .then(pl.lit("4100"))
        .when(pl.col("txn_type") == "INTEREST_CREDIT")
        .then(pl.lit("5000"))
        .when(pl.col("txn_type") == "OVERDRAFT_CHARGE_OFF")
        .then(pl.lit("5220"))
        .otherwise(None)
    )
    simple = single.filter(~pl.col("txn_type").is_in(["LOAN_PAYMENT", "LOAN_DISBURSEMENT"])).select(
        "transaction_id",
        pl.lit("deposit_entry").alias("source_type"),
        pl.col("entry_id").alias("source_id"),
        balancing_gl.alias("gl_account"),
        pl.col("amount"),
        "posted_at",
        "month",
    )
    # Loan flows through a checking account balance against the loan and interest income.
    linked = single.filter(pl.col("txn_type").is_in(["LOAN_PAYMENT", "LOAN_DISBURSEMENT"])).join(
        loan_links, left_on="reference", right_on="link_id", how="inner"
    )
    loan_side = linked.select(
        "transaction_id",
        pl.lit("loan_event").alias("source_type"),
        pl.col("event_id").alias("source_id"),
        pl.col("loan_gl").alias("gl_account"),
        pl.col("loan_amount").alias("amount"),
        "posted_at",
        "month",
    )
    return pl.concat([legs, simple, loan_side], how="vertical_relaxed")


def _loan_postings(events: pl.DataFrame, loans: pl.DataFrame) -> pl.DataFrame:
    """Postings for loan events that did not run through a checking account."""
    ev = events.join(loans.select("loan_id", "product"), on="loan_id", how="left").with_columns(
        loan_gl=pl.col("product").replace_strict(LOAN_GL, default=None),
        posted_at=pl.col("posted_date").cast(pl.Datetime("us")) + pl.duration(hours=12),
    )
    free = ev.filter(pl.col("link_id").is_null())
    rows = []
    rules = {
        "DISBURSEMENT": [("loan", 1.0), ("1000", -1.0)],
        "PAYMENT_PRINCIPAL": [("1000", 1.0), ("loan", -1.0)],
        "PAYMENT_INTEREST": [("1000", 1.0), ("4000", -1.0)],
        "CARD_PURCHASES": [("loan", 1.0), ("1000", -1.0)],
        "CARD_INTEREST": [("loan", 1.0), ("4000", -1.0)],
        "CHARGE_OFF": [("1290", 1.0), ("loan", -1.0)],
        "RECOVERY": [("1000", 1.0), ("1290", -1.0)],
    }
    for kind, legs in rules.items():
        sub = free.filter(pl.col("event_type") == kind)
        if sub.height == 0:
            continue
        for target, sign in legs:
            gl = pl.col("loan_gl") if target == "loan" else pl.lit(target)
            rows.append(
                sub.select(
                    pl.col("event_id").alias("transaction_id"),
                    pl.lit("loan_event").alias("source_type"),
                    pl.col("event_id").alias("source_id"),
                    gl.alias("gl_account"),
                    (pl.col("amount") * sign).alias("amount"),
                    "posted_at",
                    "month",
                )
            )
    return pl.concat(rows, how="vertical_relaxed")


def build_ledger(
    entries: pl.DataFrame,
    deposit_accounts: pl.DataFrame,
    deposit_balances: pl.DataFrame,
    loans: pl.DataFrame,
    events: pl.DataFrame,
    performance: pl.DataFrame,
    macro: pl.DataFrame,
    params: GeneratorParams,
    timeline: Timeline,
    rng: np.random.Generator,
) -> LedgerResult:
    """Post every sub ledger record, then add the journals that close each month."""
    loan_links = (
        events.filter(pl.col("link_id").is_not_null())
        .join(loans.select("loan_id", "product"), on="loan_id", how="left")
        .select(
            "link_id",
            "event_id",
            pl.col("product").replace_strict(LOAN_GL, default=None).alias("loan_gl"),
            pl.when(pl.col("event_type") == "DISBURSEMENT")
            .then(pl.col("amount"))
            .otherwise(-pl.col("amount"))
            .alias("loan_amount"),
            pl.col("event_type"),
        )
    )
    # Interest on a linked payment credits interest income rather than the loan.
    loan_links = loan_links.with_columns(
        loan_gl=pl.when(pl.col("event_type") == "PAYMENT_INTEREST")
        .then(pl.lit("4000"))
        .otherwise(pl.col("loan_gl"))
    ).drop("event_type")

    dep = _deposit_postings(entries, deposit_accounts, loan_links)
    lp = _loan_postings(events, loans)
    sub_postings = pl.concat(
        [dep.with_columns(pl.col("month").cast(pl.Utf8)), lp.with_columns(pl.col("month").cast(pl.Utf8))],
        how="vertical_relaxed",
    )

    # Opening balances from the sub ledgers at the window start.
    first = timeline.labels[0]
    opening_dep = (
        deposit_balances.filter(pl.col("month") == first)
        .join(deposit_accounts.select("account_id", "product"), on="account_id")
        .group_by("product")
        .agg(pl.col("opening_balance").sum())
    )
    dep_open = {r["product"]: float(r["opening_balance"]) for r in opening_dep.to_dicts()}
    perf_first = performance.filter(pl.col("month") == first).join(
        loans.select("loan_id", "product"), on="loan_id"
    )
    loan_open = {
        r["product"]: float(r["opening_balance"])
        for r in perf_first.group_by("product").agg(pl.col("opening_balance").sum()).to_dicts()
    }
    u0 = float(macro["unemployment_rate"][0])
    allowance0 = sum(loan_open.get(p, 0.0) * LOSS_RATES[p] * (1 + 0.25 * (u0 - 4.0)) for p in LOSS_RATES)
    gross_loans = sum(loan_open.values())
    deposits0 = sum(dep_open.values())
    assets0 = (gross_loans - allowance0) / (1 - 0.23)
    equity0 = 0.10 * assets0
    cash0 = 0.03 * assets0
    securities0 = 0.20 * assets0
    borrowings0 = assets0 - deposits0 - equity0
    if borrowings0 < 0:
        securities0 += -borrowings0
        borrowings0 = 0.0
    month_start = [datetime(m.year, m.month, 1) for m in timeline.months]
    journal_rows: list[dict[str, object]] = []
    jid = 0

    def journal(month_idx: int, description: str, lines: list[tuple[str, float]], day: int = 27) -> None:
        nonlocal jid
        jid += 1
        total = round(sum(a for _, a in lines), 2)
        if abs(total) > 0.005:
            raise ValueError(f"journal {description} does not balance: {total}")
        when = month_start[month_idx] + timedelta(days=day, hours=23, minutes=50)
        for gl, amount in lines:
            journal_rows.append(
                {
                    "journal_id": jid,
                    "description": description,
                    "gl_account": gl,
                    "amount": round(amount, 2),
                    "posted_at": when,
                    "month": timeline.labels[month_idx],
                }
            )

    journal(
        0,
        "Opening balances carried into the window",
        [
            ("1000", cash0),
            ("1100", securities0),
            ("1210", loan_open.get("card", 0.0)),
            ("1220", loan_open.get("mortgage", 0.0)),
            ("1200", loan_open.get("installment", 0.0)),
            ("1290", -allowance0),
            ("2000", -dep_open.get("checking", 0.0)),
            ("2010", -dep_open.get("savings", 0.0)),
            ("2020", -dep_open.get("time", 0.0)),
            ("2100", -borrowings0),
            ("3000", -equity0),
        ],
        day=0,
    )

    # Month end journals need the month's sub ledger activity, so walk forward month by month.
    sub_month = sub_postings.group_by("month", "gl_account").agg(pl.col("amount").sum())
    del sub_postings
    act = {(r["month"], r["gl_account"]): float(r["amount"]) for r in sub_month.to_dicts()}
    card_spend = (
        entries.filter(pl.col("txn_type") == "CARD_SPEND")
        .group_by("month")
        .agg((-pl.col("amount")).sum().alias("v"))
    )
    spend = {r["month"]: float(r["v"]) for r in card_spend.to_dicts()}
    purchases = (
        events.filter(pl.col("event_type") == "CARD_PURCHASES")
        .group_by("month")
        .agg(pl.col("amount").sum().alias("v"))
    )
    purch = {r["month"]: float(r["v"]) for r in purchases.to_dicts()}
    policy = macro["policy_rate"].to_numpy()
    unemployment = macro["unemployment_rate"].to_numpy()
    balances = {gl: 0.0 for gl, *_ in GL_CHART}
    for r in journal_rows:
        balances[str(r["gl_account"])] += float(r["amount"])  # type: ignore[arg-type]
    for m, label in enumerate(timeline.labels):
        opening_sec = balances["1100"]
        opening_bor = -balances["2100"]
        for gl in balances:
            balances[gl] += act.get((label, gl), 0.0)
        sec_income = round(opening_sec * 0.036 / 12.0, 2)
        journal(m, "Securities interest received", [("1000", sec_income), ("4010", -sec_income)])
        bor_cost = round(opening_bor * (policy[m] + 0.35) / 100.0 / 12.0, 2)
        if bor_cost > 0:
            journal(m, "Interest on borrowings", [("5010", bor_cost), ("1000", -bor_cost)])
        inter = round(spend.get(label, 0.0) * 0.0115 + purch.get(label, 0.0) * 0.015, 2)
        journal(m, "Card interchange settled", [("1000", inter), ("4200", -inter)])
        opex = params.opex_per_customer_month * params.customers * (1 + 0.0035 * m)
        lines = [
            ("5200", round(opex * 0.55, 2)),
            ("5210", round(opex * 0.30, 2)),
            ("5220", round(opex * 0.15, 2)),
        ]
        journal(m, "Operating expenses paid", [*lines, ("1000", -round(sum(a for _, a in lines), 2))])
        for gl, amount in [
            ("1000", sec_income - bor_cost + inter - sum(a for _, a in lines)),
            ("4010", -sec_income),
            ("5010", bor_cost),
            ("4200", -inter),
            *lines,
        ]:
            balances[gl] += amount
        # Allowance to its target; the provision is the change plus net charge offs already posted.
        u = unemployment[m]
        target = sum(
            max(balances[LOAN_GL[p]], 0.0) * LOSS_RATES[p] * (1 + 0.25 * (u - 4.0)) for p in LOSS_RATES
        )
        provision = round(target - (-balances["1290"]), 2)
        journal(m, "Provision for credit losses", [("5100", provision), ("1290", -provision)])
        balances["5100"] += provision
        balances["1290"] -= provision
        # Income tax on the month's pre tax income.
        income_gls = [g for g, _, t, *_ in GL_CHART if t in {"income", "expense"} and g != "5300"]
        month_income = -sum(act.get((label, g), 0.0) for g in income_gls) - (
            bor_cost - sec_income - inter + sum(a for _, a in lines) + provision
        )
        tax = round(0.21 * month_income, 2)
        journal(m, "Income tax accrued and paid", [("5300", tax), ("1000", -tax)])
        balances["5300"] += tax
        balances["1000"] -= tax
        # Liquidity: hold cash near three percent of assets, through securities first and borrowings second.
        assets = sum(balances[g] for g, _, t, *_ in GL_CHART if t in {"asset", "contra_asset"})
        excess = round(balances["1000"] - 0.03 * assets, 2)
        if excess > 0:
            repay = round(min(excess, -balances["2100"]), 2)
            if repay > 0:
                journal(m, "Borrowings repaid from excess cash", [("2100", repay), ("1000", -repay)])
                balances["2100"] += repay
                balances["1000"] -= repay
                excess = round(excess - repay, 2)
            if excess > 0:
                journal(m, "Excess cash invested in securities", [("1100", excess), ("1000", -excess)])
                balances["1100"] += excess
                balances["1000"] -= excess
        elif excess < 0:
            need = -excess
            sell = round(min(need, max(balances["1100"] - 0.10 * assets, 0.0)), 2)
            if sell > 0:
                journal(m, "Securities sold for liquidity", [("1000", sell), ("1100", -sell)])
                balances["1100"] -= sell
                balances["1000"] += sell
            borrow = round(need - sell, 2)
            if borrow > 0:
                journal(m, "Borrowings drawn for liquidity", [("1000", borrow), ("2100", -borrow)])
                balances["2100"] -= borrow
                balances["1000"] += borrow

    journals = (
        pl.DataFrame(journal_rows)
        .with_columns(pl.col("posted_at").cast(pl.Datetime("us")))
        # A journal line that rounds to zero cents is not written.
        .filter(pl.col("amount").abs() >= 0.005)
    )
    journal_postings = journals.select(
        pl.col("journal_id").alias("transaction_id"),
        pl.lit("gl_journal").alias("source_type"),
        pl.col("journal_id").alias("source_id"),
        "gl_account",
        "amount",
        "posted_at",
        "month",
    )
    gl_enum = pl.Enum([g for g, *_ in GL_CHART])
    source_enum = pl.Enum(["deposit_entry", "loan_event", "gl_journal"])
    month_enum = pl.Enum(timeline.labels)
    postings = pl.concat(
        [
            frame.with_columns(
                pl.col("posted_at").cast(pl.Datetime("us")),
                pl.col("gl_account").cast(gl_enum),
                pl.col("source_type").cast(source_enum),
                pl.col("month").cast(pl.Utf8).cast(month_enum),
                pl.col("transaction_id").cast(pl.Int64),
                pl.col("source_id").cast(pl.Int64),
            )
            for frame in (dep, lp, journal_postings)
        ],
        how="vertical_relaxed",
    )
    del dep, lp
    postings = postings.with_row_index("posting_id", offset=1).with_columns(
        pl.col("posting_id").cast(pl.Int64)
    )

    # Reported month end balances, as the core system would publish them.
    by_month = (
        postings.group_by("month", "gl_account")
        .agg(pl.col("amount").sum().alias("net"))
        .with_columns(pl.col("month").cast(pl.Utf8), pl.col("gl_account").cast(pl.Utf8))
    )
    grid = pl.DataFrame({"month": timeline.labels}).join(
        pl.DataFrame({"gl_account": [g for g, *_ in GL_CHART]}), how="cross"
    )
    reported = (
        grid.join(by_month, on=["month", "gl_account"], how="left")
        .with_columns(pl.col("net").fill_null(0.0))
        .sort("gl_account", "month")
        .with_columns(closing_balance=pl.col("net").cum_sum().over("gl_account").round(2))
        .drop("net")
    )
    d = params.defects
    truth_break = pl.DataFrame(
        {
            "gl_account": [d.ledger_break_account],
            "month": [d.ledger_break_month],
            "amount": [d.ledger_break_amount],
        }
    )
    if params.inject_ledger_break:
        # A liability balance reported one break amount higher (more negative in debit terms) from the break month on.
        reported = reported.with_columns(
            closing_balance=pl.when(
                (pl.col("gl_account") == d.ledger_break_account) & (pl.col("month") >= d.ledger_break_month)
            )
            .then(pl.col("closing_balance") - d.ledger_break_amount)
            .otherwise(pl.col("closing_balance"))
            .round(2)
        )
    return LedgerResult(
        chart=chart_frame(), postings=postings, journals=journals, reported=reported, truth_break=truth_break
    )
