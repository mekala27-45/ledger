"""Row level data quality rules, each with a name, a severity and a plain statement.

``quarantine`` removes the row from the staged table and writes it, with the rule
name, to data/quarantine. ``flag`` keeps the row and counts it. Every injected
generator defect has a named rule that must catch it at the injected count, and
every real dataset's known publisher issue has a rule that counts it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

Severity = str  # "quarantine" or "flag"


@dataclass(frozen=True)
class Rule:
    name: str
    table: str
    severity: Severity
    statement: str
    violates: Callable[[], pl.Expr]
    truth_defect: str | None = None


RULES: tuple[Rule, ...] = (
    Rule(
        "posting_duplicate",
        "gl_postings",
        "quarantine",
        "A posting id seen before is a duplicated posting; the first occurrence is kept.",
        lambda: ~pl.col("posting_id").is_first_distinct(),
        truth_defect="duplicated_posting",
    ),
    Rule(
        "posting_zero_amount",
        "gl_postings",
        "quarantine",
        "A posting of zero moves nothing and is not a posting.",
        lambda: pl.col("amount").abs() < 0.005,
    ),
    Rule(
        "transfer_without_counterparty",
        "deposit_entries",
        "flag",
        "An internal transfer must name the account on its other leg.",
        lambda: (pl.col("txn_type") == "INTERNAL_TRANSFER") & pl.col("counterparty_account_id").is_null(),
        truth_defect="transfer_without_counterparty",
    ),
    Rule(
        "entry_after_as_of",
        "deposit_entries",
        "quarantine",
        "No entry may be posted after the as of date.",
        lambda: pl.col("posted_at") >= pl.datetime(2026, 9, 1),
    ),
    Rule(
        "loan_balance_negative",
        "loan_performance",
        "quarantine",
        "A loan balance below zero is an overpayment the servicing system should have refunded.",
        lambda: pl.col("closing_balance") < -0.005,
    ),
    Rule(
        "loan_opened_after_as_of",
        "loans",
        "quarantine",
        "No account can be opened after the as of date.",
        lambda: pl.col("origination_date") > pl.date(2026, 8, 31),
    ),
    Rule(
        "application_income_missing",
        "loan_applications",
        "flag",
        "An application with no stated income cannot be scored on affordability.",
        lambda: pl.col("annual_income").is_null() | (pl.col("annual_income") <= 0),
    ),
    Rule(
        "card_txn_nonpositive",
        "card_transactions",
        "quarantine",
        "A card authorisation has a positive amount.",
        lambda: pl.col("amount") <= 0,
    ),
    Rule(
        "hmda_exempt_value",
        "hmda_lar",
        "flag",
        "HMDA lets smaller reporters mark some fields Exempt; the value is unknown, not zero.",
        lambda: pl.any_horizontal(pl.col("^.*_exempt$")),
    ),
    Rule(
        "hmda_income_not_available",
        "hmda_lar",
        "flag",
        "Income is NA for some application types; adjusted models drop these rows and say so.",
        lambda: pl.col("income").is_null(),
    ),
    Rule(
        "hmda_ltv_not_available",
        "hmda_lar",
        "flag",
        "Loan to value is NA for denied and withdrawn applications more often than for originations.",
        lambda: pl.col("loan_to_value_ratio").is_null(),
    ),
    Rule(
        "cfpb_response_in_progress",
        "cfpb_narratives",
        "flag",
        "A complaint still in progress has no final response and is excluded from relief outcomes.",
        lambda: pl.col("company_response_to_consumer") == "In progress",
    ),
    Rule(
        "bls_month_unavailable",
        "macro_monthly",
        "flag",
        "BLS published no October 2025 figures because of the 2025 lapse in appropriations; the month stays null.",
        lambda: (
            pl.col("unemployment_us").is_null()
            & (pl.col("month") >= "2017-01")
            & (pl.col("month") <= "2026-08")
        ),
    ),
    Rule(
        "uci_undocumented_code",
        "uci_default",
        "flag",
        "EDUCATION 0, 5, 6 and MARRIAGE 0 appear in the data but not in the published codebook.",
        lambda: pl.col("education").is_in([0, 5, 6]) | (pl.col("marriage") == 0),
    ),
    Rule(
        "baf_missing_marker",
        "baf",
        "flag",
        "The BAF suite encodes missing values as negative numbers in several fields.",
        lambda: (
            (pl.col("prev_address_months_count") < 0)
            | (pl.col("current_address_months_count") < 0)
            | (pl.col("bank_months_count") < 0)
            | (pl.col("session_length_in_minutes") < 0)
            | (pl.col("intended_balcon_amount") < 0)
        ),
    ),
)


def rules_for(table: str) -> list[Rule]:
    return [r for r in RULES if r.table == table]


def apply_rules(
    frame: pl.DataFrame, table: str
) -> tuple[pl.DataFrame, pl.DataFrame, list[dict[str, object]]]:
    """Split a table into kept rows and quarantined rows, counting every rule's hits.

    A row hit by several quarantine rules is quarantined once, under the first
    rule in declaration order.
    """
    if frame.height == 0:
        raise ValueError(f"refusing to apply rules to an empty {table} table")
    rules = rules_for(table)
    hits: list[dict[str, object]] = []
    quarantine_mask = pl.lit(False)
    reason = pl.lit(None, dtype=pl.Utf8)
    marks = frame.select([r.violates().fill_null(False).alias(r.name) for r in rules]) if rules else None
    for rule in rules:
        assert marks is not None
        count = int(marks[rule.name].sum())
        hits.append(
            {
                "table": table,
                "rule": rule.name,
                "severity": rule.severity,
                "statement": rule.statement,
                "rows_checked": frame.height,
                "rows_hit": count,
                "truth_defect": rule.truth_defect,
            }
        )
    if marks is None:
        return frame, frame.clear(), hits
    q_rules = [r for r in rules if r.severity == "quarantine"]
    for rule in reversed(q_rules):
        reason = pl.when(pl.col(f"__{rule.name}")).then(pl.lit(rule.name)).otherwise(reason)
        quarantine_mask = quarantine_mask | pl.col(f"__{rule.name}")
    work = frame.with_columns([marks[r.name].alias(f"__{r.name}") for r in q_rules])
    work = work.with_columns(quarantine_mask.alias("__q"), reason.alias("__reason"))
    kept = work.filter(~pl.col("__q")).drop([c for c in work.columns if c.startswith("__")])
    quarantined = work.filter(pl.col("__q")).rename({"__reason": "quarantine_rule"})
    quarantined = quarantined.drop([c for c in quarantined.columns if c.startswith("__")])
    return kept, quarantined, hits
