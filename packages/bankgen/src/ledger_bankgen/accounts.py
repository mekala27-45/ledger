"""Deposit accounts and their opening structure.

One checking account per customer who has one (the primary relationship), a
savings account for about half, certificates of deposit for about one in eight.
Card, installment and mortgage accounts come from loans.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import polars as pl

from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import Timeline

PRODUCT_CHECKING = "checking"
PRODUCT_SAVINGS = "savings"
PRODUCT_TIME = "time"


@dataclass
class DepositBook:
    """Account level arrays the monthly simulation walks through."""

    accounts: pl.DataFrame  # account_id, customer_id, product, open_date, term_months
    customer_index: np.ndarray  # index into customers for each account
    product: np.ndarray  # product code per account: 0 checking, 1 savings, 2 time
    open_month: np.ndarray  # index into the timeline, -1 when opened before the window
    opening_balance: np.ndarray  # balance at the window start, or the first deposit for new accounts
    checking_of_customer: np.ndarray  # account index of each customer's checking, -1 if none
    savings_of_customer: np.ndarray  # account index of each customer's savings, -1 if none
    interest_checking: np.ndarray  # bool per account


def _month_index(timeline: Timeline, day: date) -> int:
    if day < timeline.months[0]:
        return -1
    for i, m in enumerate(timeline.months):
        nxt = (
            timeline.months[i + 1]
            if i + 1 < len(timeline)
            else date(m.year + (m.month // 12), m.month % 12 + 1, 1)
        )
        if m <= day < nxt:
            return i
    return len(timeline)


def build_deposit_book(
    customers: pl.DataFrame, params: GeneratorParams, timeline: Timeline, rng: np.random.Generator
) -> DepositBook:
    n = customers.height
    start = timeline.months[0]
    window_end = timeline.months[-1] + timedelta(days=27)
    open_dates = customers["open_date"].to_list()
    segment = customers["segment"].to_numpy()

    has_checking = rng.random(n) < params.checking_share
    has_savings = rng.random(n) < params.savings_share
    has_time = rng.random(n) < params.cd_share
    # Everyone holds at least one deposit account.
    none = ~(has_checking | has_savings | has_time)
    has_checking = has_checking | none

    rows_customer: list[int] = []
    rows_product: list[int] = []
    rows_open: list[date] = []
    rows_term: list[int] = []
    for i in range(n):
        opened = open_dates[i]
        if has_checking[i]:
            rows_customer.append(i)
            rows_product.append(0)
            rows_open.append(opened)
            rows_term.append(0)
        if has_savings[i]:
            lag = int(rng.integers(0, 720)) if rng.random() < 0.5 else 0
            day = opened + timedelta(days=lag)
            if day <= window_end:
                rows_customer.append(i)
                rows_product.append(1)
                rows_open.append(day)
                rows_term.append(0)
        if has_time[i]:
            earliest = max(opened, start - timedelta(days=330))
            span = max(1, (window_end - earliest).days)
            day = earliest + timedelta(days=int(rng.integers(0, span)))
            rows_customer.append(i)
            rows_product.append(2)
            rows_open.append(day)
            rows_term.append(int(rng.choice([6, 12, 12, 12, 24])))

    customer_index = np.array(rows_customer, dtype=np.int32)
    product = np.array(rows_product, dtype=np.int8)
    open_month = np.array([_month_index(timeline, d) for d in rows_open], dtype=np.int32)
    m = len(customer_index)

    seg = segment[customer_index]
    scale = np.where(seg == "affluent", 4.0, np.where(seg == "emerging", 0.45, 1.0))
    base = np.select(
        [product == 0, product == 1, product == 2],
        [
            rng.lognormal(np.log(5_200), 0.85, m),
            rng.lognormal(np.log(12_500), 1.0, m),
            rng.lognormal(np.log(32_000), 0.7, m),
        ],
    )
    opening = np.round(base * scale, 2)
    # New accounts start from a first deposit rather than a balance.
    first_deposit = np.round(
        rng.lognormal(np.log(1_400), 0.8, m) * np.where(product == 2, 12.0, 1.0) * scale, 2
    )
    opening = np.where(open_month >= 0, first_deposit, opening)

    checking_of_customer = np.full(n, -1, dtype=np.int32)
    savings_of_customer = np.full(n, -1, dtype=np.int32)
    for idx in range(m):
        if product[idx] == 0:
            checking_of_customer[customer_index[idx]] = idx
        elif product[idx] == 1 and savings_of_customer[customer_index[idx]] == -1:
            savings_of_customer[customer_index[idx]] = idx

    interest_checking = (product == 0) & (seg == "affluent")
    customer_ids = customers["customer_id"].to_numpy()
    accounts = pl.DataFrame(
        {
            "account_id": [f"A{i:07d}" for i in range(1, m + 1)],
            "customer_id": customer_ids[customer_index],
            "product": np.array([PRODUCT_CHECKING, PRODUCT_SAVINGS, PRODUCT_TIME])[product],
            "open_date": rows_open,
            "term_months": rows_term,
            "interest_bearing": (product > 0) | interest_checking,
        }
    ).with_columns(pl.col("open_date").cast(pl.Date))
    return DepositBook(
        accounts=accounts,
        customer_index=customer_index,
        product=product,
        open_month=open_month,
        opening_balance=opening,
        checking_of_customer=checking_of_customer,
        savings_of_customer=savings_of_customer,
        interest_checking=interest_checking,
    )
