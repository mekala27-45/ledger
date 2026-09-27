"""Function 12: the board pack's one recommendation, costed.

Question for the board: is the installment approval cutoff in the right place? On
every booked loan whose twelve month outcome is observed, each candidate cutoff is
costed two ways: the losses its extra declines would have avoided (observed defaults
times the principal times loss given default) and the margin those declines would
have forgone on the loans that paid (principal times the loan rate over the policy
rate, for a year). The recommendation is the cutoff with the largest net benefit,
and the pack says what would change it.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest, Scalar

from ledger_functions.base import Context, FunctionSpec

CANDIDATES = (560, 580, 600, 620, 640)


def run(ctx: Context) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "booked installment loans with an observed twelve month outcome",
        "source": "pd_scorecard scores, loan outcomes, recoveries",
    }
    current = ctx.config.scorecard.approval_cutoff_score
    f02 = Manifest.load(ctx.paths.results / "f02" / "manifest.json")
    lgd = float(f02.raw("f02.lgd_installment"))  # type: ignore[arg-type]
    scored = pl.read_parquet(ctx.paths.models_dir / "pd_scorecard" / "applications_scored.parquet")
    loans = ctx.sql(
        """
        select o.application_id, o.default_12m, o.principal, o.interest_rate, a.policy_rate
        from marts.mart_loan_outcomes o join staging.stg_loan_applications a using (application_id)
        where o.outcome_observed
        """
    ).join(scored.select("application_id", "score"), on="application_id")
    rows: list[list[Scalar]] = []
    for cutoff in CANDIDATES:
        lo, hi = sorted((current, cutoff))
        band = loans.filter((pl.col("score") >= lo) & (pl.col("score") < hi))
        bad = band.filter(pl.col("default_12m") == 1)
        good = band.filter(pl.col("default_12m") == 0)
        loss = float((bad["principal"] * lgd).sum())
        margin = float((good["principal"] * (good["interest_rate"] - good["policy_rate"] / 100.0)).sum())
        sign = 1 if cutoff > current else -1
        # Raising the cutoff avoids the band's losses and forgoes its margin; lowering it does the reverse.
        net = sign * (loss - margin)
        rows.append([cutoff, band.height * sign, float(bad.height) * sign, loss * sign, margin * sign, net])
    table = pl.DataFrame(
        rows,
        schema=[
            "cutoff",
            "loans_changed",
            "defaults_changed",
            "loss_avoided",
            "margin_forgone",
            "net_benefit",
        ],
        orient="row",
    )
    ctx.save("cutoff_options", table)
    m.put_table(
        "f12.cutoffs",
        [
            "Cutoff",
            "Loans declined (+) or added (-)",
            "Defaults among them",
            "Losses avoided",
            "Margin forgone",
            "Net benefit",
        ],
        ["int", "int", "int", "usd0", "usd0", "usd0"],
        table.rows(),
        **gen,
    )
    best = table.sort("net_benefit", descending=True).row(0, named=True)
    m.put("f12.current_cutoff", current, "int", **gen)
    m.put("f12.recommended_cutoff", best["cutoff"], "int", **gen)
    m.put("f12.recommended_benefit", best["net_benefit"], "usd0", **gen)
    m.put("f12.recommended_loans", abs(best["loans_changed"]), "int", **gen)
    m.put("f12.recommended_defaults", abs(best["defaults_changed"]), "int", **gen)
    m.put("f12.recommended_loss_avoided", abs(best["loss_avoided"]), "usd0", **gen)
    m.put("f12.recommended_margin_forgone", abs(best["margin_forgone"]), "usd0", **gen)
    m.put("f12.loans_evaluated", loans.height, "int", **gen)
    m.put("f12.change_needed", "yes" if best["cutoff"] != current else "no", "text", **gen)
    lower = table.filter(pl.col("cutoff") < current).sort("cutoff", descending=True).row(0, named=True)
    higher = table.filter(pl.col("cutoff") > current).sort("cutoff").row(0, named=True)
    if best["cutoff"] == current:
        callout = (
            f"The current cutoff of {current} beats every alternative on loans with observed outcomes. Lowering it to "
            f"{lower['cutoff']} would have added {format_value(abs(lower['loans_changed']), 'int')} loans and lost "
            f"{format_value(abs(lower['net_benefit']), 'usd0')} net; raising it to {higher['cutoff']} would have "
            f"forgone {format_value(abs(higher['net_benefit']), 'usd0')} more margin than it saved in losses."
        )
    else:
        callout = (
            f"Moving the cutoff from {current} to {best['cutoff']} would have "
            f"{'declined' if best['cutoff'] > current else 'added'} {format_value(abs(best['loans_changed']), 'int')} "
            f"loans, {format_value(abs(best['defaults_changed']), 'int')} of which defaulted, for a net benefit of "
            f"{format_value(best['net_benefit'], 'usd0')} over their first year."
        )
    m.put("f12.lower_cutoff", lower["cutoff"], "int", **gen)
    m.put("f12.lower_net", abs(lower["net_benefit"]), "usd0", **gen)
    m.put("f12.higher_cutoff", higher["cutoff"], "int", **gen)
    m.put("f12.higher_net", abs(higher["net_benefit"]), "usd0", **gen)
    m.put_figure(
        "f12.fig_cutoffs",
        "Net benefit of each candidate cutoff, on loans with observed outcomes",
        callout,
        data="f12/cutoff_options.parquet",
        **gen,
    )


SPEC = FunctionSpec(
    code="f12",
    slug="report",
    title="The board pack",
    question="What should the board decide this quarter, what does it cost, and what would change the answer?",
    run=run,
)
