"""General ledger to sub ledger reconciliation, to the cent.

Three comparisons, each by ledger account and month:

1. The balance the ledger system reported against the running sum of the
   account's postings. A difference is a break. A break that first appears in
   one month and carries unchanged into later months is one break, located at
   the account and month where it first appears.
2. Each control account's balance against the total of its sub ledger: deposit
   accounts rebuilt from posted entries, and open loans from servicing.
3. Every posting against the sub ledger transaction it came from (in the
   warehouse tests, and counted here).

Amounts are decimals throughout, so a tie is an exact equality, not a tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import duckdb
import polars as pl


class ReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Break:
    gl_account: str
    month: str
    amount: Decimal
    months_carried: int
    kind: str  # "reported_vs_postings" or "subledger_vs_ledger"


@dataclass(frozen=True)
class Reconciliation:
    table: pl.DataFrame  # gl_account, month, balance_from_postings, reported_balance, difference, status
    subledger: pl.DataFrame  # gl_account, month, ledger, subledger, difference
    breaks: list[Break]
    unsourced_postings: int
    accounts: int
    months: int

    @property
    def clean(self) -> bool:
        return not self.breaks and self.unsourced_postings == 0


def locate(diffs: pl.DataFrame, kind: str) -> list[Break]:
    """Collapse per month differences into located breaks.

    A break starts in the month an account's difference changes; its amount is
    the change, and it is carried for as many months as the difference then
    stays at that level. A difference present from the first month is a break
    located in the first month.
    """
    out: list[Break] = []
    ordered = diffs.sort("gl_account", "month")
    for (account,), frame in ordered.group_by("gl_account", maintain_order=True):
        rows = [
            (m, Decimal(d) if d is not None else Decimal("0"))
            for m, d in frame.select("month", "difference").iter_rows()
        ]
        previous = Decimal("0")
        starts: list[tuple[int, str, Decimal]] = []
        for index, (month, diff) in enumerate(rows):
            if diff != previous:
                starts.append((index, month, diff - previous))
            previous = diff
        for k, (index, month, amount) in enumerate(starts):
            end = starts[k + 1][0] if k + 1 < len(starts) else len(rows)
            out.append(Break(str(account), month, amount, end - index, kind))
    return out


def reconcile(con: duckdb.DuckDBPyConnection) -> Reconciliation:
    postings = con.execute("select count(*) from staging.stg_gl_postings").fetchone()
    reported = con.execute("select count(*) from staging.stg_gl_reported_balances").fetchone()
    if not postings or not reported or postings[0] == 0 or reported[0] == 0:
        raise ReconciliationError(
            "refusing to reconcile an empty ledger: no postings or no reported balances"
        )
    table = con.execute(
        """
        select gl_account, month, balance_from_postings, reported_balance,
            reported_balance - balance_from_postings as difference,
            case when reported_balance = balance_from_postings then 'tied' else 'break' end as status
        from marts.mart_gl_account_month
        order by gl_account, month
        """
    ).pl()
    subledger = con.execute(
        """
        select s.gl_account, s.month, g.balance_from_postings as ledger, s.subledger_debit_balance as subledger,
            s.subledger_debit_balance - g.balance_from_postings as difference, s.accounts
        from marts.mart_subledger_month as s
        join marts.mart_gl_account_month as g using (gl_account, month)
        order by 1, 2
        """
    ).pl()
    unsourced = con.execute(
        """
        select count(*) from (
            select p.posting_id from staging.stg_gl_postings as p
            anti join staging.stg_deposit_entries as e on e.entry_id = p.source_id
            where p.source_type = 'deposit_entry'
            union all
            select p.posting_id from staging.stg_gl_postings as p
            anti join staging.stg_loan_events as l on l.event_id = p.source_id
            where p.source_type = 'loan_event'
            union all
            select p.posting_id from staging.stg_gl_postings as p
            anti join staging.stg_gl_journals as j on j.journal_id = p.source_id
            where p.source_type = 'gl_journal'
        )
        """
    ).fetchone()
    breaks = locate(table.select("gl_account", "month", "difference"), "reported_vs_postings")
    breaks += locate(subledger.select("gl_account", "month", "difference"), "subledger_vs_ledger")
    return Reconciliation(
        table=table,
        subledger=subledger,
        breaks=breaks,
        unsourced_postings=int(unsourced[0]) if unsourced else 0,
        accounts=table["gl_account"].n_unique(),
        months=table["month"].n_unique(),
    )
