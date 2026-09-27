"""Function 2: consumer lending and credit risk.

Question: how much is the installment book likely to lose, which vintages are
driving it, and how fast does delinquency roll forward? Vintage curves on months
on book, the pooled roll rate matrix, expected loss by segment from the champion
scorecard's probability with an observed over expected overlay by vintage, a
simplified lifetime (CECL style) illustration, survival curves by score band, and
the portfolio's limits with breaches marked.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Scalar
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.statistics import proportional_hazard_test

from ledger_functions.base import Context, FunctionSpec

BANDS = (
    (0, 560, "under 560"),
    (560, 600, "560 to 599"),
    (600, 640, "600 to 639"),
    (640, 10_000, "640 and over"),
)
LIMITS = (
    ("loose_share", "Loosened vintages' share of installment balances", 0.35, "at_most", "pct1"),
    ("dq30_installment", "Installment balances 30 or more days past due", 0.04, "at_most", "pct2"),
    ("npl_ratio", "Nonperforming loans to gross loans", 0.01, "at_most", "pct2"),
    ("mortgage_share", "Mortgages' share of gross loans", 0.75, "at_most", "pct1"),
)


def band_of(score: pl.Expr) -> pl.Expr:
    expr: Any = pl.when(score < BANDS[0][1]).then(pl.lit(BANDS[0][2]))
    for lo, hi, label in BANDS[1:]:
        expr = expr.when((score >= lo) & (score < hi)).then(pl.lit(label))
    out: pl.Expr = expr.otherwise(pl.lit(BANDS[-1][2]))
    return out


def run(ctx: Context) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "Harborline installment loans",
        "source": "warehouse marts",
    }
    as_of = ctx.config.calendar.as_of.strftime("%Y-%m")

    # Vintage curves on months on book.
    vint = ctx.sql("select * from marts.mart_vintage_curves order by vintage, months_on_book")
    ctx.save("vintages", vint)
    at12 = vint.filter(pl.col("months_on_book") == 12)
    loose = ["2024Q4", "2025Q1"]
    loose_12 = at12.filter(pl.col("vintage").is_in(loose))["cumulative_default_rate"].mean()
    before = at12.filter(pl.col("vintage") < "2024Q4")["cumulative_default_rate"].mean()
    m.put("f02.loose_12mob", loose_12, "pct1", **gen)  # type: ignore[arg-type]
    m.put("f02.prior_12mob", before, "pct1", **gen)  # type: ignore[arg-type]
    m.put_figure(
        "f02.fig_vintages",
        "Cumulative default rate by months on book, one line per origination quarter",
        f"The two vintages written under the loosened cutoff (2024Q4 and 2025Q1) reached "
        f"{format_value(loose_12, 'pct1')} cumulative default by twelve months on book, against "  # type: ignore[arg-type]
        f"{format_value(before, 'pct1')} for the vintages before them. Each curve stops where its "  # type: ignore[arg-type]
        f"youngest loan's history ends; nothing is extrapolated.",
        data="f02/vintages.parquet",
        **gen,
    )

    # Roll rates, pooled over the window, buckets in order.
    rolls = ctx.sql("select * from marts.mart_roll_rates_pooled order by from_order, to_order")
    ctx.save("roll_rates", rolls)

    def rate(a: str, b: str) -> float:
        r = rolls.filter((pl.col("from_bucket") == a) & (pl.col("to_bucket") == b))["rate"]
        return float(r[0]) if r.len() else 0.0

    for a, b, key in (
        ("current", "30", "cur_30"),
        ("30", "60", "r30_60"),
        ("60", "90+", "r60_90"),
        ("90+", "charged_off", "r90_co"),
        ("30", "current", "cure30"),
    ):
        m.put(f"f02.roll_{key}", rate(a, b), "pct2", **gen)
    m.put_figure(
        "f02.fig_rolls",
        "Monthly transitions between delinquency buckets",
        f"A current loan rolls to 30 days past due with probability {format_value(rate('current', '30'), 'pct2')} "
        f"a month; once there it rolls on to 60 with probability {format_value(rate('30', '60'), 'pct1')} and "
        f"cures with {format_value(rate('30', 'current'), 'pct1')}. The diagonal dominates every row, as it must "
        f"in a book that mostly pays.",
        data="f02/roll_rates.parquet",
        **gen,
    )

    # Loss given default from the generated recoveries, stated as its source.
    rec = ctx.sql(
        "select recovery_rate from marts.mart_recoveries where product = 'installment' and months_since = 24"
    )
    lgd = 1.0 - float(rec["recovery_rate"][0])
    m.put("f02.lgd_installment", lgd, "pct1", **{**gen, "source": "mart_recoveries at 24 months"})

    # Expected loss by segment on the open installment book at the as of date.
    scored = pl.read_parquet(ctx.paths.models_dir / "pd_scorecard" / "applications_scored.parquet")
    book = ctx.sql(
        """
        select f.loan_id, f.vintage, f.closing_balance as ead, f.state, l.application_id
        from marts.fct_loan_month as f join marts.dim_loan as l using (loan_id)
        where f.product = 'installment' and f.month = ? and f.state not in ('charged_off', 'paid_off', 'matured')
        """,
        [as_of],
    ).join(scored.select("application_id", "score", "pd_champion"), on="application_id", how="left")
    outcomes = ctx.sql(
        "select vintage, loan_id, default_12m from marts.mart_loan_outcomes where outcome_observed"
    )
    observed = outcomes.join(
        scored.join(
            ctx.sql("select loan_id, application_id from marts.dim_loan"), on="application_id"
        ).select("loan_id", "pd_champion"),
        on="loan_id",
    )
    overlay = (
        observed.group_by("vintage")
        .agg(
            (pl.col("default_12m").mean() / pl.col("pd_champion").mean()).alias("overlay"),
            pl.len().alias("loans"),
        )
        .sort("vintage")
    )
    recent = float(overlay.tail(3)["overlay"].mean())  # type: ignore[arg-type]
    book = (
        book.join(overlay.select("vintage", "overlay"), on="vintage", how="left")
        .with_columns(
            pl.col("overlay").fill_null(recent),
            band=band_of(pl.col("score")),
        )
        .with_columns(
            pd_adjusted=(pl.col("pd_champion") * pl.col("overlay")).clip(0, 1),
        )
        .with_columns(el=pl.col("pd_adjusted") * lgd * pl.col("ead"))
    )
    ctx.save("overlay_by_vintage", overlay)
    m.put("f02.overlay_recent", recent, "float2", **gen)
    seg = (
        book.group_by("band")
        .agg(
            pl.len().alias("loans"),
            pl.col("ead").sum(),
            pl.col("pd_adjusted").mean().alias("pd"),
            pl.col("el").sum(),
        )
        .with_columns(el_rate=pl.col("el") / pl.col("ead"))
    )
    order = {label: i for i, (_, _, label) in enumerate(BANDS)}
    seg = seg.with_columns(o=pl.col("band").replace_strict(order, return_dtype=pl.Int32)).sort("o").drop("o")
    ctx.save("expected_loss", seg)
    m.put_table(
        "f02.el_table",
        ["Score band", "Loans", "Exposure", "PD (with overlay)", "LGD", "Expected loss", "EL rate"],
        ["text", "int", "usdm", "pct2", "pct1", "usd0", "pct2"],
        [
            [r["band"], r["loans"], r["ead"], r["pd"], lgd, r["el"], r["el_rate"]]
            for r in seg.iter_rows(named=True)
        ],
        **gen,
    )
    total_el = float(book["el"].sum())
    raw_el = float((book["pd_champion"].fill_null(0.0) * lgd * book["ead"]).sum())
    m.put("f02.el_raw_total", raw_el, "usd0", **gen)
    m.put("f02.el_overlay_build", total_el - raw_el, "usd0", **gen)
    total_ead = float(book["ead"].sum())
    m.put("f02.el_total", total_el, "usd0", **gen)
    m.put("f02.ead_total", total_ead, "usdm", **gen)
    m.put("f02.el_rate", total_el / total_ead, "pct2", **gen)

    # CECL style lifetime loss, simplified and labelled so.
    cecl = cecl_illustration(ctx, book, vint, lgd)
    ctx.save("cecl_by_vintage", cecl)
    m.put_table(
        "f02.cecl_table",
        ["Vintage", "Exposure", "12 month PD", "Lifetime PD", "Macro factor", "Lifetime loss"],
        ["text", "usdm", "pct2", "pct2", "float2", "usd0"],
        cecl.rows(),
        **{**gen, "source": "simplified CECL illustration"},
    )
    m.put("f02.cecl_total", float(cecl["lifetime_loss"].sum()), "usd0", **gen)

    # Survival by score band.
    survival(ctx, scored)

    # Limits.
    lim_rows: list[list[Scalar]] = []
    port = ctx.sql(
        "select product, sum(balance) balance, sum(balance_30_plus) b30, sum(balance_90_plus) b90 "
        "from marts.mart_portfolio_monthly where month = ? group by 1",
        [as_of],
    )
    totals = {r["product"]: r for r in port.iter_rows(named=True)}
    gross = sum(float(r["balance"]) for r in totals.values())
    inst = totals["installment"]
    measured = {
        "loose_share": float(book.filter(pl.col("vintage").is_in(loose))["ead"].sum()) / total_ead,
        "dq30_installment": float(inst["b30"] or 0) / float(inst["balance"]),
        "npl_ratio": sum(float(r["b90"] or 0) for r in totals.values()) / gross,
        "mortgage_share": float(totals["mortgage"]["balance"]) / gross,
    }
    for key, label, limit, comparison, fmt in LIMITS:
        value = measured[key]
        breach = value > limit if comparison == "at_most" else value < limit
        lim_rows.append([label, value, limit, "BREACH" if breach else "within"])
        m.put(f"f02.limit_{key}", value, fmt, **gen)
    m.put_table(
        "f02.limits",
        ["Limit", "Measured", "Limit value", "Status"],
        ["text", "pct2", "pct2", "text"],
        lim_rows,
        **gen,
    )
    ctx.save(
        "limits", pl.DataFrame(lim_rows, schema=["limit", "measured", "limit_value", "status"], orient="row")
    )


def cecl_illustration(ctx: Context, book: pl.DataFrame, vint: pl.DataFrame, lgd: float) -> pl.DataFrame:
    """Lifetime PD from the pooled vintage curve's shape, with a macro factor from the 2026 baseline.

    Simplifications, stated where used: the lifetime multiple is the ratio of
    cumulative default at 30 months on book to 12 months on the vintages that have
    reached 30; the macro factor applies the recovered macro sensitivity to the gap
    between the supervisory baseline's average unemployment over eight quarters and
    the generated history's average; the result is not an audited estimate.
    """
    full = vint.filter(pl.col("months_on_book").is_in([12, 30]))
    ripe = full.group_by("vintage").agg(pl.len()).filter(pl.col("len") == 2)["vintage"]
    wide = full.filter(pl.col("vintage").is_in(ripe.to_list())).pivot(
        on="months_on_book", index="vintage", values="cumulative_default_rate"
    )
    multiple = float((wide["30"] / wide["12"]).mean())  # type: ignore[arg-type]
    beta_row = pl.read_parquet(ctx.paths.models_dir / "known_parameters.parquet").filter(
        pl.col("parameter").str.starts_with("Macro sensitivity")
    )
    beta = float(beta_row["estimate"][0])
    baseline = ctx.sql(
        "select avg(unemployment_rate) u from (select * from marts.mart_scenarios where scenario = 'baseline' "
        "order by quarter limit 8)"
    )["u"][0]
    history = ctx.sql("select avg(unemployment_rate) u from marts.dim_month")["u"][0]
    factor = float(np.exp(beta * (float(baseline) - float(history))))
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "mixed",
        "population": "open installment loans; macro factor from the 2026 supervisory baseline",
        "source": "simplified CECL illustration",
    }
    m.put("f02.cecl_multiple", multiple, "float2", **gen)
    m.put("f02.cecl_macro_factor", factor, "float3", **gen)
    m.put("f02.cecl_baseline_unemployment", float(baseline) / 100, "pct1", **gen)
    out = (
        book.group_by("vintage")
        .agg(pl.col("ead").sum(), pl.col("pd_adjusted").mean().alias("pd12"))
        .sort("vintage")
    )
    return (
        out.with_columns(
            lifetime_pd=(pl.col("pd12") * multiple).clip(0, 1),
            macro_factor=pl.lit(factor),
        )
        .with_columns(lifetime_loss=pl.col("ead") * pl.col("lifetime_pd") * factor * lgd)
        .select("vintage", "ead", "pd12", "lifetime_pd", "macro_factor", "lifetime_loss")
    )


def survival(ctx: Context, scored: pl.DataFrame) -> None:
    m = ctx.manifest
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "booked installment loans",
        "source": "lifelines",
    }
    loans = (
        ctx.sql(
            """
        select o.loan_id, o.application_id, o.vintage, o.origination_index, o.months_to_default,
            l.term_months, dm.unemployment_rate,
            (select max(f.months_on_book) from marts.fct_loan_month f where f.loan_id = o.loan_id) as last_mob
        from marts.mart_loan_outcomes o
        join marts.dim_loan l using (loan_id)
        join marts.dim_month dm on dm.month = o.origination_month
        """
        )
        .join(scored.select("application_id", "score"), on="application_id", how="left")
        .drop_nulls("score")
    )
    frame = loans.with_columns(
        duration=pl.when(pl.col("months_to_default").is_not_null())
        .then(pl.col("months_to_default"))
        .otherwise(pl.col("last_mob"))
        .cast(pl.Float64)
        .clip(0.5, None),
        event=pl.col("months_to_default").is_not_null().cast(pl.Int8),
        band=band_of(pl.col("score")),
        loose=pl.col("vintage").is_in(["2024Q4", "2025Q1"]).cast(pl.Int8),
    )
    curves = []
    at_risk_rows: list[list[Scalar]] = []
    for _, _, label in BANDS:
        part = frame.filter(pl.col("band") == label)
        if part.height < 20:
            continue
        kmf = KaplanMeierFitter().fit(part["duration"].to_numpy(), part["event"].to_numpy(), label=label)
        sf = kmf.survival_function_.reset_index()
        sf.columns = ["months", "survival"]
        curves.append(pl.from_pandas(sf).with_columns(band=pl.lit(label)))
        table = kmf.event_table.reset_index()
        row: list[Scalar] = [label]
        for t in (0, 6, 12, 18, 24):
            row.append(
                int(table[table["event_at"] >= t]["at_risk"].iloc[0]) if (table["event_at"] >= t).any() else 0
            )
        at_risk_rows.append(row)
        m.put(f"f02.km_12_{label.replace(' ', '_')}", float(kmf.predict(12)), "pct1", **gen)
    ctx.save("survival_curves", pl.concat(curves))
    m.put_table(
        "f02.at_risk",
        ["Score band", "At risk at 0", "6", "12", "18", "24"],
        ["text", "int", "int", "int", "int", "int"],
        at_risk_rows,
        **gen,
    )
    # Sorted, because the warehouse returns rows in no fixed order and the fit should not care.
    cox_frame = (
        frame.sort("loan_id")
        .select(
            score_per_20=pl.col("score") / 20.0,
            loose="loose",
            unemployment=pl.col("unemployment_rate"),
            duration="duration",
            event="event",
        )
        .to_pandas()
    )
    cph = CoxPHFitter().fit(cox_frame, duration_col="duration", event_col="event")
    # The Kaplan Meier time transform, R's cox.zph default: tied durations get the same
    # transformed time. The rank transform numbers tied events in row order, and with
    # whole month durations that made the p values change from one run to the next.
    test = proportional_hazard_test(cph, cox_frame, time_transform="km")
    rows: list[list[Scalar]] = []
    for name in ("score_per_20", "loose", "unemployment"):
        rows.append(
            [
                {
                    "score_per_20": "Score, per 20 points",
                    "loose": "Loosened vintage",
                    "unemployment": "Unemployment at origination, per point",
                }[name],
                float(np.exp(cph.params_[name])),
                float(np.exp(cph.confidence_intervals_.loc[name].iloc[0])),
                float(np.exp(cph.confidence_intervals_.loc[name].iloc[1])),
                float(test.summary.loc[name, "p"]),
            ]
        )
    m.put_table(
        "f02.cox",
        ["Covariate", "Hazard ratio", "95% low", "95% high", "PH test p value"],
        ["text", "float3", "float3", "float3", "float3"],
        rows,
        **gen,
    )
    m.put("f02.cox_concordance", float(cph.concordance_index_), "float3", **gen)
    m.put_figure(
        "f02.fig_survival",
        "Share of loans not yet defaulted, by score band at application",
        f"Twelve months after origination, {format_value(m.raw('f02.km_12_640_and_over'), 'pct1')} of loans scored "
        f"640 and over have not defaulted, against {format_value(m.raw('f02.km_12_under_560'), 'pct1')} of those "
        f"under 560. The Cox model's proportional hazards test is published beside it.",
        data="f02/survival_curves.parquet",
        **gen,
    )


SPEC = FunctionSpec(
    code="f02",
    slug="lending",
    title="Consumer lending and credit risk",
    question="How much is the installment book likely to lose, which vintages drive it, and how fast does delinquency roll?",
    run=run,
)
