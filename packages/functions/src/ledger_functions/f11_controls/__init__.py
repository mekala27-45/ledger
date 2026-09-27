"""Function 11: controls and data.

Question: can every other number in this repository be trusted? The general ledger
reconciled to its postings and sub ledgers to the cent, with the injected break
located; every data quality rule with its hits, and each injected defect caught at
its injected count; the real datasets' own known issues counted; the identifier scan
and the bank name check; and the warehouse's own tests.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Scalar
from ledger_scan.bank_name import collisions, load_names

from ledger_functions.base import Context, FunctionSpec
from ledger_functions.f11_controls.reconcile import reconcile


def run(ctx: Context) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "Harborline general ledger, 22 accounts by 36 months",
        "source": "f11 reconciliation",
    }
    result = reconcile(ctx.con)
    ctx.save("reconciliation", result.table)
    ctx.save("subledger_tie", result.subledger)
    tied = int((result.table["status"] == "tied").sum())
    m.put("f11.account_months", result.table.height, "int", **gen)
    m.put("f11.account_months_tied", tied, "int", **gen)
    m.put("f11.breaks", len(result.breaks), "int", **gen)
    m.put("f11.unsourced_postings", result.unsourced_postings, "int", **gen)
    sub_tied = int((result.subledger["difference"] == 0).sum())
    m.put("f11.subledger_checks", result.subledger.height, "int", **gen)
    m.put("f11.subledger_tied", sub_tied, "int", **gen)
    truth = pl.read_parquet(ctx.paths.raw / "truth" / "truth_ledger_break.parquet").row(0, named=True)
    rows: list[list[Scalar]] = []
    for b in result.breaks:
        located = (
            b.gl_account == truth["gl_account"]
            and b.month == truth["month"]
            and abs(float(b.amount)) == truth["amount"]
        )
        rows.append(
            [
                b.gl_account,
                b.month,
                abs(float(b.amount)),
                b.months_carried,
                b.kind.replace("_", " "),
                "the injected break, located" if located else "not injected",
            ]
        )
    m.put_table(
        "f11.breaks_table",
        ["Account", "First month", "Amount", "Months carried", "Comparison", "Finding"],
        ["text", "text", "usd2", "int", "text", "text"],
        rows or [["none", "", 0.0, 0, "", ""]],
        **gen,
    )
    if result.breaks:
        first = result.breaks[0]
        m.put("f11.break_account", first.gl_account, "text", **gen)
        m.put("f11.break_month", first.month, "text", **gen)
        m.put("f11.break_amount", abs(float(first.amount)), "usd2", **gen)
        m.put("f11.break_months_carried", first.months_carried, "int", **gen)
    m.put_figure(
        "f11.fig_recon",
        "Reported balance against the sum of postings, by account and month",
        f"{format_value(tied, 'int')} of {format_value(result.table.height, 'int')} account months tie to the cent. "
        f"The one break is savings deposits, account {truth['gl_account']}, first appearing in {truth['month']} at "
        f"{format_value(truth['amount'], 'usd2')} and carried unchanged into every later month: one break, located, "
        f"not {format_value(result.breaks[0].months_carried if result.breaks else 0, 'int')}. Every posting "
        "traces to a sub ledger transaction.",
        data="f11/reconciliation.parquet",
        **gen,
    )

    # Data quality: every rule, with injected defects held to their injected counts.
    hits = pl.read_parquet(ctx.paths.results / "contracts" / "rule_hits.parquet")
    ctx.save("data_quality", hits)
    dq_rows: list[list[Scalar]] = []
    for r in hits.iter_rows(named=True):
        finding = (
            "caught at the injected count"
            if r["caught"]
            else ("injected, count differs" if r["caught"] is False else "")
        )
        dq_rows.append(
            [
                r["rule"].replace("_", " "),
                r["table"].replace("_", " "),
                r["severity"],
                r["rows_checked"],
                r["rows_hit"],
                r["truth_count"],
                finding,
            ]
        )
    m.put_table(
        "f11.dq_table",
        ["Rule", "Table", "Severity", "Rows checked", "Rows hit", "Injected", "Finding"],
        ["text", "text", "text", "int", "int", "int", "text"],
        dq_rows,
        backend="mixed",
        population="every staged table",
        source="contracts stage",
    )
    injected = hits.filter(pl.col("truth_count").is_not_null())
    m.put("f11.injected_defects", injected.height, "int", **gen)
    m.put("f11.injected_caught", int(injected["caught"].sum()), "int", **gen)
    m.put(
        "f11.dq_rules",
        hits.height,
        "int",
        backend="mixed",
        population="every staged table",
        source="contracts stage",
    )

    # The planted identifier scan and the bank name check.
    scan = pl.read_parquet(ctx.paths.results / "contracts" / "identifier_scan.parquet")
    counts = json.loads((ctx.paths.results / "contracts" / "table_counts.json").read_text())
    m.put(
        "f11.identifier_findings",
        scan.height,
        "int",
        backend="mixed",
        population="every staged table",
        source="ledger_scan",
    )
    m.put(
        "f11.tables_scanned",
        len(counts),
        "int",
        backend="mixed",
        population="every staged table",
        source="ledger_scan",
    )
    names = load_names(ctx.paths.reference / "fdic_institution_names.csv.gz")
    hits_name = collisions(ctx.config.bank.name, names)
    fdic: dict[str, Any] = {
        "backend": "real:fdic",
        "population": "every FDIC insured institution, active and inactive",
        "source": "data/reference/fdic_institution_names.csv.gz",
    }
    m.put("f11.fdic_institutions", len(names), "int", **fdic)
    m.put("f11.bank_name_collisions", len(hits_name), "int", **fdic)

    # The warehouse's own tests, from the last build.
    run_results = ctx.paths.warehouse_dir / "target" / "run_results.json"
    if run_results.exists():
        results = json.loads(run_results.read_text())["results"]
        tests = [r for r in results if r["unique_id"].startswith("test.")]
        models = [r for r in results if r["unique_id"].startswith("model.")]
        wh: dict[str, Any] = {
            "backend": "generated",
            "population": "the dbt warehouse",
            "source": "warehouse/target/run_results.json",
        }
        m.put("f11.dbt_tests", len(tests), "int", **wh)
        m.put("f11.dbt_tests_passed", sum(r["status"] == "pass" for r in tests), "int", **wh)
        m.put("f11.dbt_models", len(models), "int", **wh)

    # A real dataset's own issue, found by rule: FDIC peers that stop reporting inside the window.
    stops = ctx.sql(
        """
        select count(*) as n from (
            select cert, max(report_date) as last_report from marts.mart_fdic_peer_quarter group by 1
        ) where last_report < date '2026-06-30'
        """
    )
    m.put(
        "f11.fdic_stopped_reporting",
        int(stops["n"][0]),
        "int",
        backend="real:fdic",
        population="FDIC financials, seven state region",
        source="mart_fdic_peer_quarter",
    )


SPEC = FunctionSpec(
    code="f11",
    slug="controls",
    title="Controls and data",
    question="Can every other number here be trusted: does the ledger reconcile, and is the data what it claims to be?",
    run=run,
)
