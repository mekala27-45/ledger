"""The contracts stage: validate, quarantine by rule, scan, and stage.

Raw generated tables (data/raw/generated), the card stream (data/raw/sparkov)
and the real datasets (data/external, normalised by ingest.py) all pass through
here before the warehouse reads anything. The stage writes:

    data/staged/generated/*.parquet   kept rows
    data/staged/sparkov/card_transactions.parquet
    data/staged/real/*.parquet        typed real tables
    data/quarantine/<table>.parquet   quarantined rows with the rule that took them
    results/contracts/rule_hits.parquet, identifier_scan.parquet
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pandera.polars as pa
import polars as pl
from ledger_core.paths import Paths
from ledger_scan.tables import Finding, load_names, scan_frame

from ledger_contracts.ingest import stage_all
from ledger_contracts.rules import apply_rules
from ledger_contracts.schemas import GENERATED, REAL, SPARKOV

ORDER = (
    "customers",
    "deposit_accounts",
    "deposit_rates",
    "loan_applications",
    "loans",
    "loan_performance",
    "loan_events",
    "gl_chart",
    "gl_journals",
    "gl_reported_balances",
    "hmda_style_applications",
    "macro_path",
    "deposit_entries",
    "deposit_balances",
    "gl_postings",
)


class ContractError(RuntimeError):
    pass


def _utf8(frame: pl.DataFrame) -> pl.DataFrame:
    """Enum and categorical columns become text so contracts and DuckDB see one type."""
    casts = [
        pl.col(c).cast(pl.Utf8)
        for c, t in frame.schema.items()
        if isinstance(t, pl.Enum) or t == pl.Categorical
    ]
    return frame.with_columns(casts) if casts else frame


def validate(frame: pl.DataFrame, schema: pa.DataFrameSchema) -> None:
    try:
        schema.validate(frame, lazy=True)
    except pa.errors.SchemaErrors as exc:
        raise ContractError(f"{schema.name}: {exc.failure_cases.head(10)}") from exc


def balance_roll_check(balances: pl.DataFrame, entries: pl.DataFrame) -> pl.DataFrame:
    """Closing balance must equal opening plus the month's posted entries, to the cent."""
    activity = entries.group_by("account_id", "month").agg(pl.col("amount").sum().alias("activity"))
    joined = balances.join(activity, on=["account_id", "month"], how="left").with_columns(
        pl.col("activity").fill_null(0.0)
    )
    return joined.with_columns(
        closing_from_entries=(pl.col("opening_balance") + pl.col("activity")).round(2),
    ).with_columns(balance_rolls=(pl.col("closing_balance") - pl.col("closing_from_entries")).abs() < 0.005)


def run_contracts(p: Paths, *, include_real: bool = True, include_cards: bool = True) -> dict[str, object]:
    staged_gen = p.staged / "generated"
    staged_gen.mkdir(parents=True, exist_ok=True)
    p.quarantine.mkdir(parents=True, exist_ok=True)
    out = p.results / "contracts"
    out.mkdir(parents=True, exist_ok=True)
    names = load_names(p.staged / "sparkov" / "person_names.txt.gz")
    hits: list[dict[str, object]] = []
    findings: list[Finding] = []
    counts: dict[str, dict[str, int]] = {}

    entries_for_roll: pl.DataFrame | None = None
    for table in ORDER:
        path = p.generated / f"{table}.parquet"
        if not path.exists():
            raise ContractError(f"missing raw table {path}; run `make generate` first")
        frame = _utf8(pl.read_parquet(path))
        validate(frame, GENERATED[table])
        if table == "deposit_balances":
            assert entries_for_roll is not None
            checked = balance_roll_check(frame, entries_for_roll)
            broken = int((~checked["balance_rolls"]).sum())
            hits.append(
                {
                    "table": table,
                    "rule": "balance_does_not_roll",
                    "severity": "flag",
                    "statement": "Closing balance must equal opening plus the month's posted entries, to the cent; "
                    "the staged table carries the balance rebuilt from entries beside the reported one.",
                    "rows_checked": frame.height,
                    "rows_hit": broken,
                    "truth_defect": "balance_does_not_roll",
                }
            )
            kept = (
                checked.rename({"closing_balance": "closing_balance_reported"})
                .with_columns(closing_balance=pl.col("closing_from_entries"))
                .drop("closing_from_entries", "activity")
            )
            quarantined = kept.clear()
            entries_for_roll = None
        else:
            kept, quarantined, table_hits = apply_rules(frame, table) if frame.height else (frame, frame, [])
            hits += table_hits
        if table == "deposit_entries":
            entries_for_roll = kept.select("account_id", "month", "amount")
        if table in {"customers", "deposit_accounts", "loans", "loan_applications", "deposit_entries"}:
            findings += scan_frame(kept, table, names)
        kept.write_parquet(staged_gen / f"{table}.parquet", compression="zstd")
        if quarantined.height:
            quarantined.write_parquet(p.quarantine / f"{table}.parquet", compression="zstd")
        counts[table] = {
            "rows_in": frame.height,
            "rows_kept": kept.height,
            "rows_quarantined": quarantined.height,
        }
        del frame, kept, quarantined
        gc.collect()

    if include_cards:
        cards = _utf8(pl.read_parquet(p.sparkov / "card_transactions.parquet"))
        validate(cards, SPARKOV)
        kept, quarantined, table_hits = apply_rules(cards, "card_transactions")
        hits += table_hits
        findings += scan_frame(kept.drop("merchant_name"), "card_transactions", names)
        (p.staged / "sparkov").mkdir(parents=True, exist_ok=True)
        kept.write_parquet(p.staged / "sparkov" / "card_transactions.parquet", compression="zstd")
        counts["card_transactions"] = {
            "rows_in": cards.height,
            "rows_kept": kept.height,
            "rows_quarantined": quarantined.height,
        }
        del cards, kept, quarantined
        gc.collect()

    if include_real:
        for staged in stage_all(p):
            frame = pl.read_parquet(staged.path)
            schema = REAL.get(staged.name)
            if schema is not None:
                validate(frame, schema)
            from ledger_contracts.rules import rules_for

            if rules_for(staged.name):
                _, _, table_hits = apply_rules(frame, staged.name)
                hits += table_hits
            names_apply = staged.name not in {
                "cfpb_narratives",
                "cfpb_companies",
                "fdic_institutions",
                "fdic_financials",
            }
            findings += scan_frame(frame, staged.name, names, names_apply=names_apply)
            counts[staged.name] = {"rows_in": frame.height, "rows_kept": frame.height, "rows_quarantined": 0}
            del frame
            gc.collect()

    truth_path = p.raw / "truth" / "truth_defects.parquet"
    truth = (
        {r["defect"]: r["count"] for r in pl.read_parquet(truth_path).to_dicts()}
        if truth_path.exists()
        else {}
    )
    hit_frame = (
        pl.DataFrame(hits)
        .with_columns(
            truth_count=pl.col("truth_defect").replace_strict(truth, default=None, return_dtype=pl.Int64)
        )
        .with_columns(
            caught=pl.when(pl.col("truth_count").is_null())
            .then(None)
            .otherwise(pl.col("rows_hit") == pl.col("truth_count"))
        )
    )
    hit_frame.write_parquet(out / "rule_hits.parquet")
    scan = pl.DataFrame(
        [{"table": f.table, "column": f.column, "kind": f.kind, "sample": f.sample} for f in findings],
        schema={"table": pl.Utf8, "column": pl.Utf8, "kind": pl.Utf8, "sample": pl.Utf8},
    )
    scan.write_parquet(out / "identifier_scan.parquet")
    (out / "table_counts.json").write_text(json.dumps(counts, indent=1, sort_keys=True) + "\n")
    missed = hit_frame.filter(pl.col("caught") == False)  # noqa: E712
    if missed.height:
        raise ContractError(f"injected defects not caught at their injected count: {missed.to_dicts()}")
    if scan.height:
        raise ContractError(f"identifier scan found {scan.height} identifiers: {scan.head(5).to_dicts()}")
    return {"tables": counts, "rule_hits": hit_frame.height, "identifiers": scan.height}


def main(root: Path | None = None) -> int:
    from ledger_core.paths import paths

    p = paths() if root is None else Paths(root)
    summary = run_contracts(p)
    print(json.dumps({"tables": len(summary["tables"]), "identifiers": summary["identifiers"]}))  # type: ignore[arg-type]
    return 0
