"""Pandera contracts for every raw table and every mart the site reads.

A contract states types, nullability, keys and value domains. Row level rules
that decide whether a row is quarantined or flagged live in rules.py, because a
contract failure stops the pipeline and a rule hit does not.
"""

from __future__ import annotations

import pandera.polars as pa
import polars as pl

C = pa.Column
Check = pa.Check

MONTH = Check.str_matches(r"^\d{4}-\d{2}$")
NONNEG = Check.ge(0)


def _schema(
    name: str, columns: dict[str, pa.Column], *, unique: list[str] | None = None
) -> pa.DataFrameSchema:
    return pa.DataFrameSchema(columns, name=name, strict=False, unique=unique)


GENERATED: dict[str, pa.DataFrameSchema] = {
    "customers": _schema(
        "customers",
        {
            "customer_id": C(pl.Utf8, unique=True),
            "open_date": C(pl.Date),
            "birth_year": C(pl.Int64, Check.in_range(1920, 2008)),
            "state": C(pl.Utf8, Check.isin(["NJ", "NY", "PA"])),
            "county_fips": C(pl.Utf8, Check.str_length(5, 5), nullable=True),
            "segment": C(pl.Utf8, Check.isin(["mass", "affluent", "emerging"])),
            "annual_income": C(pl.Float64, NONNEG),
        },
    ),
    "deposit_accounts": _schema(
        "deposit_accounts",
        {
            "account_id": C(pl.Utf8, unique=True),
            "customer_id": C(pl.Utf8),
            "product": C(pl.Utf8, Check.isin(["checking", "savings", "time"])),
            "open_date": C(pl.Date),
            "term_months": C(pl.Int64, NONNEG),
            "closed_month": C(pl.Utf8, nullable=True),
        },
    ),
    "deposit_entries": _schema(
        "deposit_entries",
        {
            "entry_id": C(pl.Int64),
            "transaction_id": C(pl.Int64),
            "month": C(pl.Utf8, MONTH),
            "posted_at": C(pl.Datetime("us")),
            "txn_type": C(pl.Utf8),
            "amount": C(pl.Float64, Check.ne(0.0)),
            "account_id": C(pl.Utf8),
            "counterparty_account_id": C(pl.Utf8, nullable=True),
            "counterparty_id": C(pl.Utf8, nullable=True),
        },
    ),
    "deposit_balances": _schema(
        "deposit_balances",
        {
            "account_id": C(pl.Utf8),
            "month": C(pl.Utf8, MONTH),
            "opening_balance": C(pl.Float64),
            "closing_balance": C(pl.Float64),
        },
        unique=["account_id", "month"],
    ),
    "loan_applications": _schema(
        "loan_applications",
        {
            "application_id": C(pl.Utf8, unique=True),
            "application_date": C(pl.Date),
            "bureau_score": C(pl.Int64, Check.in_range(300, 850)),
            "dti": C(pl.Float64, Check.in_range(0, 1.5)),
            "revolving_utilization": C(pl.Float64, Check.in_range(0, 1.5)),
            "annual_income": C(pl.Float64, NONNEG),
            "loan_amount": C(pl.Float64, Check.gt(0)),
            "decision": C(pl.Utf8, Check.isin(["approved", "declined"])),
            "booked": C(pl.Boolean),
        },
    ),
    "loans": _schema(
        "loans",
        {
            "loan_id": C(pl.Utf8, unique=True),
            "product": C(pl.Utf8, Check.isin(["installment", "card", "mortgage"])),
            "origination_date": C(pl.Date),
            "principal": C(pl.Float64, NONNEG),
            "interest_rate": C(pl.Float64, Check.in_range(0, 0.4)),
            "customer_id": C(pl.Utf8),
        },
    ),
    "loan_performance": _schema(
        "loan_performance",
        {
            "loan_id": C(pl.Utf8),
            "month": C(pl.Utf8, MONTH),
            "months_on_book": C(pl.Int32, NONNEG),
            "state": C(pl.Utf8),
            "opening_balance": C(pl.Float64),
            "closing_balance": C(pl.Float64),
            "charge_off_amount": C(pl.Float64, NONNEG),
            "recovery_amount": C(pl.Float64, NONNEG),
        },
        unique=["loan_id", "month"],
    ),
    "loan_events": _schema(
        "loan_events",
        {
            "event_id": C(pl.Int64, unique=True),
            "loan_id": C(pl.Utf8),
            "month": C(pl.Utf8, MONTH),
            "event_type": C(pl.Utf8),
            "amount": C(pl.Float64),
        },
    ),
    "gl_chart": _schema(
        "gl_chart",
        {
            "gl_account": C(pl.Utf8, unique=True),
            "account_type": C(
                pl.Utf8, Check.isin(["asset", "contra_asset", "liability", "equity", "income", "expense"])
            ),
            "normal_balance": C(pl.Utf8, Check.isin(["debit", "credit"])),
        },
    ),
    "gl_postings": _schema(
        "gl_postings",
        {
            "posting_id": C(pl.Int64),
            "transaction_id": C(pl.Int64),
            "source_type": C(pl.Utf8, Check.isin(["deposit_entry", "loan_event", "gl_journal"])),
            "source_id": C(pl.Int64),
            "gl_account": C(pl.Utf8),
            "amount": C(pl.Float64),
            "month": C(pl.Utf8, MONTH),
        },
    ),
    "gl_journals": _schema(
        "gl_journals",
        {
            "journal_id": C(pl.Int64),
            "gl_account": C(pl.Utf8),
            "amount": C(pl.Float64),
            "month": C(pl.Utf8, MONTH),
        },
    ),
    "gl_reported_balances": _schema(
        "gl_reported_balances",
        {
            "month": C(pl.Utf8, MONTH),
            "gl_account": C(pl.Utf8),
            "closing_balance": C(pl.Float64),
        },
        unique=["month", "gl_account"],
    ),
    "hmda_style_applications": _schema(
        "hmda_style_applications",
        {
            "hmda_application_id": C(pl.Utf8, unique=True),
            "month": C(pl.Utf8, MONTH),
            "action_taken": C(pl.Utf8),
        },
    ),
    "macro_path": _schema(
        "macro_path",
        {
            "month": C(pl.Utf8, MONTH, unique=True),
            "unemployment_rate": C(pl.Float64, Check.in_range(0, 30)),
            "policy_rate": C(pl.Float64, Check.in_range(0, 25)),
        },
    ),
    "deposit_rates": _schema("deposit_rates", {"month": C(pl.Utf8, MONTH, unique=True)}),
}

SPARKOV = _schema(
    "card_transactions",
    {
        "txn_id": C(pl.Int64, unique=True),
        "card_key": C(pl.Utf8, Check.str_matches(r"^K[0-9a-f]{10}$")),
        "transaction_time": C(pl.Datetime("us")),
        "category": C(pl.Utf8),
        "amount": C(pl.Float64, Check.gt(0)),
        "merchant_key": C(pl.Utf8),
        "merchant_lat": C(pl.Float64, Check.in_range(-90, 90)),
        "merchant_long": C(pl.Float64, Check.in_range(-180, 180)),
        "customer_lat": C(pl.Float64, Check.in_range(-90, 90)),
        "customer_long": C(pl.Float64, Check.in_range(-180, 180)),
        "gender": C(pl.Utf8, Check.isin(["F", "M"])),
        "birth_year": C(pl.Int32, Check.in_range(1900, 2012)),
        "is_fraud": C(pl.Int8, Check.isin([0, 1])),
    },
)

REAL: dict[str, pa.DataFrameSchema] = {
    "hmda_lar": _schema(
        "hmda_lar",
        {
            "activity_year": C(pl.Int32, Check.isin([2024, 2025])),
            "lei": C(pl.Utf8, Check.str_length(20, 20)),
            "state_code": C(pl.Utf8, Check.eq("NJ")),
            "action_taken": C(pl.Int8, Check.isin([1, 2, 3, 4, 5])),
            "loan_amount": C(pl.Float64, NONNEG, nullable=True),
            "income": C(pl.Float64, nullable=True),
            "derived_race": C(pl.Utf8),
            "derived_ethnicity": C(pl.Utf8),
            "derived_sex": C(pl.Utf8),
        },
    ),
    "cfpb_narratives": _schema(
        "cfpb_narratives",
        {
            "complaint_id": C(pl.Utf8, unique=True),
            "date_received": C(pl.Date),
            "product": C(pl.Utf8),
            "consumer_complaint_narrative": C(pl.Utf8, Check.str_length(min_value=1)),
            "company": C(pl.Utf8),
        },
    ),
    "fdic_institutions": _schema(
        "fdic_institutions",
        {"CERT": C(pl.Int64, unique=True), "NAME": C(pl.Utf8), "ACTIVE": C(pl.Boolean)},
    ),
    "fdic_financials": _schema(
        "fdic_financials",
        {
            "CERT": C(pl.Int64),
            "report_date": C(pl.Date),
            "ASSET": C(pl.Int64, NONNEG),
            "STALP": C(pl.Utf8, Check.isin(["CT", "DE", "MA", "MD", "NJ", "NY", "PA"])),
        },
        unique=["CERT", "report_date"],
    ),
    "uci_default": _schema(
        "uci_default",
        {
            "account_id": C(pl.Int64, unique=True),
            "limit_bal": C(pl.Float64, Check.gt(0)),
            "age": C(pl.Int64, Check.in_range(18, 100)),
            "default_next_month": C(pl.Int8, Check.isin([0, 1])),
        },
    ),
    "baf": _schema(
        "baf",
        {
            "fraud_bool": C(pl.Int64, Check.isin([0, 1])),
            "customer_age": C(pl.Int64, Check.in_range(10, 100)),
            "month": C(pl.Int64, Check.in_range(0, 7)),
            "variant": C(pl.Utf8, Check.isin(["base", "variant_ii"])),
        },
    ),
    "macro_monthly": _schema("macro_monthly", {"month": C(pl.Utf8, MONTH, unique=True)}),
    "frb_scenarios": _schema(
        "frb_scenarios",
        {
            "scenario": C(pl.Utf8, Check.isin(["historic", "baseline", "severely_adverse"])),
            "quarter": C(pl.Utf8, Check.str_matches(r"^\d{4}Q[1-4]$")),
            "unemployment_rate": C(pl.Float64, Check.in_range(0, 30)),
        },
        unique=["scenario", "quarter"],
    ),
}
