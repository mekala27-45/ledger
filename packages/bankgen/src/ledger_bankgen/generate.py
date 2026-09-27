"""Run the whole generator and write the raw tables Harborline's core systems would hold.

Truth tables go to a separate folder with a ``truth_`` prefix. Nothing in the
warehouse, the models or the site reads them; only the known parameter recovery
checks, the typology recall scorecard and the reconciliation tests do.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from ledger_bankgen.accounts import build_deposit_book
from ledger_bankgen.customers import build_customers
from ledger_bankgen.deposits import TYPES, ScheduledEntries, simulate_deposits
from ledger_bankgen.ledger import build_ledger
from ledger_bankgen.loans import build_loan_book
from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import build_macro, build_timeline
from ledger_bankgen.typologies import inject


@dataclass
class GenerationSummary:
    tables: dict[str, int]
    seconds: float


def _link_loans_to_checking(
    events: pl.DataFrame,
    loans: pl.DataFrame,
    customers: pl.DataFrame,
    checking_of_customer: np.ndarray,
    timeline_labels: list[str],
) -> tuple[pl.DataFrame, ScheduledEntries]:
    """Borrowers with a checking account pay from it and are disbursed into it."""
    cust_index = {cid: i for i, cid in enumerate(customers["customer_id"].to_list())}
    loan_cust = loans.select("loan_id", "customer_id", "product").with_columns(
        checking=pl.Series([int(checking_of_customer[cust_index[c]]) for c in loans["customer_id"].to_list()])
    )
    ev = events.join(loan_cust, on="loan_id", how="left")
    linkable = (
        (pl.col("checking") >= 0)
        & ~pl.col("is_payoff")
        & (
            ((pl.col("event_type") == "DISBURSEMENT") & (pl.col("product") != "card"))
            | pl.col("event_type").is_in(["PAYMENT_PRINCIPAL", "PAYMENT_INTEREST"])
        )
    )
    ev = ev.with_columns(
        link_group=pl.when(pl.col("event_type") == "DISBURSEMENT").then(pl.lit("D")).otherwise(pl.lit("P"))
    )
    links = (
        ev.filter(linkable)
        .group_by("loan_id", "month", "link_group")
        .agg(
            pl.col("amount").sum().alias("total"),
            pl.col("posted_date").min().alias("posted_date"),
            pl.col("checking").first().alias("checking"),
        )
        .sort("loan_id", "month", "link_group")
        .with_row_index("link_id", offset=70_000_000)
        .with_columns(pl.col("link_id").cast(pl.Int64))
    )
    ev = ev.join(
        links.select("loan_id", "month", "link_group", "link_id"),
        on=["loan_id", "month", "link_group"],
        how="left",
    )
    ev = ev.with_columns(link_id=pl.when(linkable).then(pl.col("link_id")).otherwise(None)).drop(
        "customer_id", "product", "checking", "link_group"
    )
    month_index = {m: i for i, m in enumerate(timeline_labels)}
    starts = {m: int(m[5:7]) for m in timeline_labels}
    sched = ScheduledEntries()
    for group, kind, sign in (("D", "LOAN_DISBURSEMENT", 1.0), ("P", "LOAN_PAYMENT", -1.0)):
        part = links.filter(pl.col("link_group") == group)
        if part.height == 0:
            continue
        months = np.array([month_index[m] for m in part["month"].to_list()])
        days = np.array([min(d.day - 1, 24) for d in part["posted_date"].to_list()])
        seconds = days * 86400 + 9 * 3600
        sched.add(
            months,
            part["checking"].to_numpy(),
            part["total"].to_numpy() * sign,
            TYPES[kind],
            seconds,
            ref=part["link_id"].to_numpy(),
        )
        if group == "D":
            # Loan proceeds go where the loan was for: a dealer, another lender, a contractor.
            sched.add(
                months,
                part["checking"].to_numpy(),
                -np.round(part["total"].to_numpy() * 0.97, 2),
                TYPES["ACH_OUT"],
                seconds + 2 * 86400,
            )
    del starts
    return ev, sched


def _merge(a: ScheduledEntries, b: ScheduledEntries) -> ScheduledEntries:
    out = ScheduledEntries()
    for src in (a, b):
        for field in (
            "month",
            "account",
            "amount",
            "kind",
            "seconds",
            "cp_account",
            "cp_external",
            "branch",
            "group",
            "ref",
        ):
            getattr(out, field).extend(getattr(src, field))
    return out


def generate(
    params: GeneratorParams, out_dir: Path, truth_dir: Path, *, verbose: bool = True
) -> GenerationSummary:
    started = time.time()
    rng = np.random.default_rng(params.seed)
    timeline = build_timeline(params)
    macro = build_macro(params, timeline, rng)

    def say(message: str) -> None:
        if verbose:
            print(f"[bankgen {time.time() - started:6.1f}s] {message}", flush=True)

    customers = build_customers(params, timeline, rng)
    say(f"customers {customers.height:,}")
    book = build_deposit_book(customers, params, timeline, rng)
    say(f"deposit accounts {book.accounts.height:,}")
    loanbook = build_loan_book(customers, params, timeline, macro, rng)
    events = loanbook.events.with_row_index("event_id", offset=1).with_columns(
        pl.col("event_id").cast(pl.Int64)
    )
    say(
        f"applications {loanbook.applications.height:,}, loans {loanbook.loans.height:,}, loan months {loanbook.performance.height:,}"
    )
    events, loan_sched = _link_loans_to_checking(
        events, loanbook.loans, customers, book.checking_of_customer, timeline.labels
    )
    injection = inject(customers, book, params, timeline, rng)
    say(f"typology episodes {injection.truth['episode_id'].n_unique() if injection.truth.height else 0}")
    deposits = simulate_deposits(
        customers,
        book,
        params,
        timeline,
        macro,
        _merge(loan_sched, injection.scheduled),
        injection.friends,
        injection.cash_intensive,
        rng,
    )
    say(f"deposit entries {deposits.entries.height:,}")
    # A linked loan flow whose checking account had closed is settled in cash instead.
    posted_links = set(
        deposits.entries.filter(pl.col("txn_type").is_in(["LOAN_PAYMENT", "LOAN_DISBURSEMENT"]))[
            "reference"
        ].to_list()
    )
    events = events.with_columns(
        link_id=pl.when(pl.col("link_id").is_in(list(posted_links))).then(pl.col("link_id")).otherwise(None)
    )
    led = build_ledger(
        deposits.entries,
        book.accounts,
        deposits.balances,
        loanbook.loans,
        events,
        loanbook.performance,
        macro,
        params,
        timeline,
        rng,
    )
    say(f"postings {led.postings.height:,}")

    entries = deposits.entries
    balances = deposits.balances
    postings = led.postings
    defects: list[dict[str, object]] = []
    if params.inject_defects:
        d = params.defects
        dup = postings.sample(fraction=d.duplicated_posting_rate, seed=params.seed)
        postings = pl.concat([postings, dup])
        defects.append({"defect": "duplicated_posting", "count": dup.height})
        transfers = entries.filter(
            (pl.col("txn_type") == "INTERNAL_TRANSFER") & pl.col("counterparty_account_id").is_not_null()
        )
        drop_cp = transfers.sample(fraction=d.missing_counterparty_rate * 10, seed=params.seed + 1)[
            "entry_id"
        ]
        entries = entries.with_columns(
            counterparty_account_id=pl.when(pl.col("entry_id").is_in(drop_cp.to_list()))
            .then(None)
            .otherwise(pl.col("counterparty_account_id"))
        )
        defects.append({"defect": "transfer_without_counterparty", "count": len(drop_cp)})
        broken = balances.sample(fraction=d.non_rolling_balance_rate, seed=params.seed + 2).select(
            "account_id", "month"
        )
        balances = (
            balances.join(
                broken.with_columns(pl.lit(True).alias("_b")), on=["account_id", "month"], how="left"
            )
            .with_columns(
                closing_balance=pl.when(pl.col("_b"))
                .then(pl.col("closing_balance") + 100.0)
                .otherwise(pl.col("closing_balance"))
            )
            .drop("_b")
        )
        defects.append({"defect": "balance_does_not_roll", "count": broken.height})
        if params.inject_ledger_break:
            defects.append({"defect": "ledger_break", "count": 1})

    out_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "customers": customers.drop("latent_risk"),
        "deposit_accounts": book.accounts.join(deposits.closures, on="account_id", how="left"),
        "deposit_entries": entries,
        "deposit_balances": balances,
        "deposit_rates": deposits.rates,
        "loan_applications": loanbook.applications,
        "loans": loanbook.loans,
        "loan_performance": loanbook.performance,
        "loan_events": events,
        "gl_chart": led.chart,
        "gl_postings": postings,
        "gl_journals": led.journals,
        "gl_reported_balances": led.reported,
        "hmda_style_applications": loanbook.mortgage_applications,
        "macro_path": macro,
    }
    counts: dict[str, int] = {}
    for name, frame in tables.items():
        frame.write_parquet(out_dir / f"{name}.parquet", compression="zstd")
        counts[name] = frame.height
    truth = {
        "truth_customers": customers.select("customer_id", "latent_risk"),
        "truth_loans": loanbook.truth,
        "truth_typologies": injection.truth.with_columns(
            customer_id=pl.Series(
                customers["customer_id"].to_numpy()[injection.truth["customer_index"].to_numpy()]
            ),
            account_id=pl.Series(
                book.accounts["account_id"].to_numpy()[injection.truth["account_index"].to_numpy()]
            ),
        ).drop("customer_index", "account_index")
        if injection.truth.height
        else injection.truth,
        "truth_ledger_break": led.truth_break,
        "truth_attrition_hazard": deposits.truth_attrition,
        "truth_defects": pl.DataFrame(defects) if defects else pl.DataFrame({"defect": [], "count": []}),
    }
    for name, frame in truth.items():
        frame.write_parquet(truth_dir / f"{name}.parquet", compression="zstd")
    (truth_dir / "truth_parameters.json").write_text(
        json.dumps(params.model_dump(mode="json"), indent=2) + "\n"
    )
    elapsed = time.time() - started
    say(f"done in {elapsed:.1f}s")
    return GenerationSummary(tables=counts, seconds=elapsed)
