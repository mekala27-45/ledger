"""Function 3: fair lending and adverse action.

Question: in the real New Jersey HMDA data, are applicants of some races,
ethnicities or sexes denied mortgages more often than comparable applicants, and
does the bank's own scorecard keep protected attributes out of its decisions and
its adverse action reasons?

Method: unadjusted denial rate ratios with log intervals; adjusted odds ratios from
a logistic regression on the controls the public file allows, with lender fixed
effects; Benjamini and Hochberg across each family of comparisons; the county map
unadjusted and as observed over expected denials; the denial reasons the lenders
reported; and the proxy list checked against every model's features.

Limitation, stated wherever a figure appears: the public file has no credit score
and no automated underwriting result, the two variables a lender's own analysis
would control for first, so an adjusted gap here is a question for a lender's data,
not a finding.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Scalar
from ledger_fairness.disparity import (
    Z95,
    adjusted_odds_ratios,
    benjamini_hochberg,
    expected_rates,
    unadjusted_table,
)
from ledger_scorecard.policy_files import load_proxies, model_feature_lists, proxy_hits

from ledger_functions.base import Context, FunctionSpec

RACE_REFERENCE = "White non Hispanic"
SEX_REFERENCE = "Male"
MIN_LENDER_APPLICATIONS = 200
MIN_OUTCOMES = 10
MIN_LEVEL = 100
NUMERIC = ("log_income", "income_missing", "log_amount")
CATEGORICAL = ("ltv_band", "dti", "loan_type", "loan_purpose", "aus", "lender", "year")

# New Jersey's counties by FIPS code, as the Census Bureau publishes them.
NJ_COUNTIES = {
    "34001": "Atlantic",
    "34003": "Bergen",
    "34005": "Burlington",
    "34007": "Camden",
    "34009": "Cape May",
    "34011": "Cumberland",
    "34013": "Essex",
    "34015": "Gloucester",
    "34017": "Hudson",
    "34019": "Hunterdon",
    "34021": "Mercer",
    "34023": "Middlesex",
    "34025": "Monmouth",
    "34027": "Morris",
    "34029": "Ocean",
    "34031": "Passaic",
    "34033": "Salem",
    "34035": "Somerset",
    "34037": "Sussex",
    "34039": "Union",
    "34041": "Warren",
}

# HMDA denial reason codes, from the filing instructions.
DENIAL_REASONS = {
    "1": "Debt to income ratio",
    "2": "Employment history",
    "3": "Credit history",
    "4": "Collateral",
    "5": "Insufficient cash",
    "6": "Unverifiable information",
    "7": "Credit application incomplete",
    "8": "Mortgage insurance denied",
    "9": "Other",
}
LOAN_TYPES = {"1": "conventional", "2": "FHA", "3": "VA", "4": "USDA"}
LOAN_PURPOSES = {"1": "home purchase", "31": "refinance", "32": "cash out refinance"}


def odds(rate: float) -> float:
    return rate / (1 - rate)


def prepare(apps: pl.DataFrame) -> pl.DataFrame:
    """Encode the controls: logs, bands and explicit missing levels, never a dropped row."""
    # A lender gets its own fixed effect only with enough applications and both outcomes;
    # a lender that denied nobody has an estimate at minus infinity and stops the fit.
    counts = apps.group_by("lei").agg(pl.len().alias("n"), pl.col("denied").cast(pl.Int64).sum().alias("d"))
    big = set(
        counts.filter(
            (pl.col("n") >= MIN_LENDER_APPLICATIONS)
            & (pl.col("d") >= MIN_OUTCOMES)
            & (pl.col("n") - pl.col("d") >= MIN_OUTCOMES)
        )["lei"].to_list()
    )
    aus_counts = apps.group_by("aus_1").len()
    common_aus = set(aus_counts.filter(pl.col("len") >= MIN_LEVEL)["aus_1"].cast(pl.Utf8).to_list())
    ltv = pl.col("loan_to_value_ratio")
    return apps.with_columns(
        denied=pl.col("denied").cast(pl.Int8),
        log_income=pl.when(pl.col("income") > 0).then(pl.col("income").log()).otherwise(0.0),
        income_missing=(pl.col("income").is_null() | (pl.col("income") <= 0)).cast(pl.Float64),
        log_amount=pl.col("loan_amount").log(),
        ltv_band=pl.when(ltv.is_null() | (ltv <= 0) | (ltv > 200))
        .then(pl.lit("missing"))
        .when(ltv <= 60)
        .then(pl.lit("60 or less"))
        .when(ltv <= 80)
        .then(pl.lit("60 to 80"))
        .when(ltv <= 90)
        .then(pl.lit("80 to 90"))
        .when(ltv <= 95)
        .then(pl.lit("90 to 95"))
        .otherwise(pl.lit("over 95")),
        dti=pl.col("dti_band").fill_null("missing"),
        loan_type=pl.col("loan_type").cast(pl.Utf8),
        loan_purpose=pl.col("loan_purpose").cast(pl.Utf8),
        # Rare codes (exempt, five applications) join HMDA's own "other" code, 5; a level
        # of five approvals and no denials has no finite estimate.
        aus=pl.when(pl.col("aus_1").cast(pl.Utf8).is_in(list(common_aus)))
        .then(pl.col("aus_1").cast(pl.Utf8))
        .otherwise(pl.lit("5")),
        lender=pl.when(pl.col("lei").is_in(list(big)))
        .then(pl.col("lei"))
        .otherwise(pl.lit("smaller lenders")),
        year=pl.col("activity_year").cast(pl.Utf8),
        sex_group=pl.when(pl.col("derived_sex").is_in(["Male", "Female", "Joint"]))
        .then(pl.col("derived_sex"))
        .otherwise(pl.lit("Not provided")),
    )


def run(ctx: Context) -> None:
    m = ctx.manifest
    hmda: dict[str, Any] = {
        "backend": "real:hmda",
        "population": "New Jersey HMDA 2024 and 2025, first lien owner occupied home purchase and refinance "
        "applications on 1 to 4 unit homes that reached a decision",
        "source": "mart_hmda_applications",
    }
    rules = ctx.paths.rules
    protected = load_proxies(rules)
    apps = ctx.sql(
        """
        select activity_year, lei, county_fips, derived_race, derived_ethnicity, derived_sex, denied,
            loan_type, loan_purpose, loan_amount, loan_to_value_ratio, income, dti_band, aus_1,
            denial_reason_1, race_ethnicity_group
        from marts.mart_hmda_applications
        order by activity_year, lei, county_fips, loan_amount, income
        """
    )
    frame = prepare(apps)
    n = frame.height
    denials = int(frame["denied"].sum())
    m.put("f03.applications", n, "int", **hmda)
    m.put("f03.denials", denials, "int", **hmda)
    m.put("f03.denial_rate", denials / n, "pct1", **hmda)
    m.put("f03.lenders", frame["lei"].n_unique(), "int", **hmda)
    years = sorted(frame["year"].unique().to_list())
    m.put(
        "f03.years",
        " and ".join([", ".join(years[:-1]), years[-1]]) if len(years) > 1 else years[0],
        "text",
        **hmda,
    )
    m.put("f03.lenders_with_fixed_effect", frame["lender"].n_unique() - 1, "int", **hmda)
    m.put(
        "f03.fixed_effect_share",
        float((frame["lender"] != "smaller lenders").mean()),  # type: ignore[arg-type]
        "pct1",
        **hmda,
    )

    # Unadjusted: each group's denial rate over its reference group's.
    race = unadjusted_table(frame, "denied", "race_ethnicity_group", RACE_REFERENCE).with_columns(
        dimension=pl.lit("race and ethnicity")
    )
    sex = unadjusted_table(frame, "denied", "sex_group", SEX_REFERENCE).with_columns(dimension=pl.lit("sex"))
    raw = pl.concat([race, sex])
    tested = raw.filter(pl.col("p_value").is_not_null())
    q = benjamini_hochberg(tested["p_value"].to_list())
    raw = raw.join(
        tested.select("dimension", "group").with_columns(q_value=pl.Series(q)),
        on=["dimension", "group"],
        how="left",
    )
    ctx.save("unadjusted", raw)
    rows: list[list[Scalar]] = []
    for r in raw.sort("dimension", "rate", descending=[False, True]).iter_rows(named=True):
        reference = r["p_value"] is None
        rows.append(
            [
                r["dimension"],
                r["group"] + (" (reference)" if reference else ""),
                r["applications"],
                r["denials"],
                r["rate"],
                None if reference else r["ratio"],
                r["low"],
                r["high"],
                r["q_value"],
            ]
        )
    m.put_table(
        "f03.unadjusted",
        [
            "Dimension",
            "Group",
            "Applications",
            "Denials",
            "Denial rate",
            "Ratio to reference",
            "95% low",
            "95% high",
            "BH q value",
        ],
        ["text", "text", "int", "int", "pct1", "float2", "float2", "float2", "float4"],
        rows,
        **hmda,
    )
    black = raw.filter((pl.col("dimension") == "race and ethnicity") & (pl.col("group") == "Black")).row(
        0, named=True
    )
    hisp = raw.filter(
        (pl.col("dimension") == "race and ethnicity") & (pl.col("group") == "Hispanic or Latino")
    ).row(0, named=True)
    white = raw.filter(
        (pl.col("dimension") == "race and ethnicity") & (pl.col("group") == RACE_REFERENCE)
    ).row(0, named=True)
    m.put("f03.black_rate", black["rate"], "pct1", **hmda)
    m.put("f03.white_rate", white["rate"], "pct1", **hmda)
    m.put("f03.hispanic_rate", hisp["rate"], "pct1", **hmda)
    m.put("f03.black_ratio", black["ratio"], "float2", **hmda)
    m.put("f03.black_or_raw", odds(black["rate"]) / odds(white["rate"]), "float2", **hmda)
    asian = raw.filter((pl.col("dimension") == "race and ethnicity") & (pl.col("group") == "Asian")).row(
        0, named=True
    )
    m.put("f03.asian_ratio", asian["ratio"], "float2", **hmda)
    m.put("f03.hispanic_ratio", hisp["ratio"], "float2", **hmda)
    m.put("f03.comparisons", len(q), "int", **hmda)
    m.put("f03.significant_unadjusted", int((q < 0.05).sum()), "int", **hmda)

    # Adjusted: one model, both bases, the controls the public file allows, lender fixed effects.
    adjusted, r2 = adjusted_odds_ratios(
        frame,
        "denied",
        {"race_ethnicity_group": RACE_REFERENCE, "sex_group": SEX_REFERENCE},
        NUMERIC,
        CATEGORICAL,
        protected,
    )
    qa = benjamini_hochberg(adjusted["p_value"].to_list())
    adjusted = adjusted.with_columns(q_value=pl.Series(qa))
    ctx.save("adjusted", adjusted)
    # Unadjusted odds ratios with Woolf intervals, so the chart compares like with like.
    forest_rows = []
    for dim, col, ref_group in (
        ("race_ethnicity_group", "race and ethnicity", RACE_REFERENCE),
        ("sex_group", "sex", SEX_REFERENCE),
    ):
        ref = raw.filter((pl.col("dimension") == col) & (pl.col("p_value").is_null())).row(0, named=True)
        for r in raw.filter((pl.col("dimension") == col) & pl.col("p_value").is_not_null()).iter_rows(
            named=True
        ):
            a_, b_ = r["denials"], r["applications"] - r["denials"]
            c_, d_ = ref["denials"], ref["applications"] - ref["denials"]
            log_or = math.log((a_ * d_) / (b_ * c_))
            se = math.sqrt(1 / a_ + 1 / b_ + 1 / c_ + 1 / d_)
            adj = adjusted.filter((pl.col("dimension") == dim) & (pl.col("group") == r["group"])).row(
                0, named=True
            )
            forest_rows.append(
                {
                    "dimension": col,
                    "group": r["group"],
                    "reference": ref_group,
                    "raw_or": math.exp(log_or),
                    "raw_low": math.exp(log_or - Z95 * se),
                    "raw_high": math.exp(log_or + Z95 * se),
                    "adj_or": adj["odds_ratio"],
                    "adj_low": adj["low"],
                    "adj_high": adj["high"],
                    "adj_q": adj["q_value"],
                }
            )
    ctx.save("forest", pl.DataFrame(forest_rows))
    names = {"race_ethnicity_group": "race and ethnicity", "sex_group": "sex"}
    m.put_table(
        "f03.adjusted",
        ["Dimension", "Group", "Odds ratio", "95% low", "95% high", "BH q value", "Finding at q < 0.05"],
        ["text", "text", "float2", "float2", "float2", "float4", "text"],
        [
            [
                names[r["dimension"]],
                r["group"],
                r["odds_ratio"],
                r["low"],
                r["high"],
                r["q_value"],
                ("higher odds of denial" if r["odds_ratio"] > 1 else "lower odds of denial")
                if r["q_value"] < 0.05
                else "not distinguishable from the reference",
            ]
            for r in adjusted.sort("dimension", "odds_ratio", descending=[False, True]).iter_rows(named=True)
        ],
        **{**hmda, "source": "logistic regression with lender fixed effects on mart_hmda_applications"},
    )
    adj_black = adjusted.filter(pl.col("group") == "Black").row(0, named=True)
    adj_hisp = adjusted.filter(pl.col("group") == "Hispanic or Latino").row(0, named=True)
    m.put("f03.black_or", adj_black["odds_ratio"], "float2", **hmda)
    m.put("f03.black_or_low", adj_black["low"], "float2", **hmda)
    m.put("f03.black_or_high", adj_black["high"], "float2", **hmda)
    m.put("f03.hispanic_or", adj_hisp["odds_ratio"], "float2", **hmda)
    m.put("f03.asian_or", adjusted.filter(pl.col("group") == "Asian")["odds_ratio"][0], "float2", **hmda)
    m.put("f03.pseudo_r2", r2, "float3", **hmda)
    m.put("f03.significant_adjusted", int((qa < 0.05).sum()), "int", **hmda)
    m.put("f03.adjusted_comparisons", len(qa), "int", **hmda)
    m.put_figure(
        "f03.fig_disparity",
        "Denial disparities against the reference group, before and after adjustment",
        f"Black applicants were denied at {format_value(black['rate'], 'pct1')} against "
        f"{format_value(white['rate'], 'pct1')} for white non Hispanic applicants, a ratio of "
        f"{format_value(black['ratio'], 'float2')}, or an odds ratio of "
        f"{format_value(odds(black['rate']) / odds(white['rate']), 'float2')}. With income, loan size, loan to value, "
        "debt to income, "
        f"loan type and purpose, the underwriting system and the lender held fixed, the odds ratio is "
        f"{format_value(adj_black['odds_ratio'], 'float2')} ({format_value(adj_black['low'], 'float2')} to "
        f"{format_value(adj_black['high'], 'float2')}). Adjustment narrows the gap and does not close it; the "
        "public file has no credit score or underwriting result, so what remains is a question for a lender's own "
        "data, not a finding.",
        data="f03/adjusted.parquet",
        **hmda,
    )

    # The county map: the unadjusted denial rate, and observed over expected denials.
    expected = expected_rates(frame, "denied", NUMERIC, CATEGORICAL, protected)
    state_rate = denials / n
    county = (
        frame.with_columns(expected=pl.Series(expected))
        .group_by("county_fips")
        .agg(
            pl.len().alias("applications"),
            pl.col("denied").cast(pl.Int64).sum().alias("denials"),
            pl.col("expected").sum().alias("expected"),
        )
        .filter(pl.col("county_fips").is_in(list(NJ_COUNTIES)))
        .with_columns(
            county=pl.col("county_fips").replace_strict(NJ_COUNTIES),
            rate=pl.col("denials") / pl.col("applications"),
            observed_over_expected=pl.col("denials") / pl.col("expected"),
        )
        .with_columns(adjusted_rate=pl.col("observed_over_expected") * state_rate)
        .sort("county_fips")
    )
    ctx.save("county", county)
    hi = county.sort("rate", descending=True).row(0, named=True)
    lo = county.sort("rate").row(0, named=True)
    hi_adj = county.sort("observed_over_expected", descending=True).row(0, named=True)
    m.put("f03.counties", county.height, "int", **hmda)
    m.put("f03.county_high", hi["county"], "text", **hmda)
    m.put("f03.county_high_rate", hi["rate"], "pct1", **hmda)
    m.put("f03.county_low", lo["county"], "text", **hmda)
    m.put("f03.county_low_rate", lo["rate"], "pct1", **hmda)
    m.put("f03.county_high_adjusted", hi_adj["county"], "text", **hmda)
    m.put("f03.county_high_oe", hi_adj["observed_over_expected"], "float2", **hmda)
    m.put_table(
        "f03.county_table",
        ["County", "Applications", "Denial rate", "Observed over expected", "Adjusted rate"],
        ["text", "int", "pct1", "float2", "pct1"],
        [
            [r["county"], r["applications"], r["rate"], r["observed_over_expected"], r["adjusted_rate"]]
            for r in county.sort("rate", descending=True).iter_rows(named=True)
        ],
        **hmda,
    )
    m.put_figure(
        "f03.fig_map",
        "Denial rate by county, unadjusted and adjusted for the application mix",
        f"Unadjusted, {hi['county']} County denies the most ({format_value(hi['rate'], 'pct1')}) and "
        f"{lo['county']} the least ({format_value(lo['rate'], 'pct1')}) against "
        f"{format_value(state_rate, 'pct1')} for the state. Adjusted for each county's applications and lenders, "
        f"{hi_adj['county']} still denies {format_value(hi_adj['observed_over_expected'], 'float2')} times the "
        "denials its mix predicts. County is a map, never a model input: it is on the proxy list.",
        data="f03/county.parquet",
        **hmda,
    )

    # The reasons lenders gave, overall and by group.
    reasons = (
        frame.filter(pl.col("denied") == 1)
        .with_columns(
            reason=pl.col("denial_reason_1").cast(pl.Utf8).replace_strict(DENIAL_REASONS, default=None)
        )
        .filter(pl.col("reason").is_not_null())
        .group_by("race_ethnicity_group", "reason")
        .len()
        .with_columns(share=pl.col("len") / pl.col("len").sum().over("race_ethnicity_group"))
        .sort("race_ethnicity_group", "len", descending=[False, True])
    )
    ctx.save("denial_reasons", reasons)
    overall = (
        reasons.group_by("reason")
        .agg(pl.col("len").sum())
        .with_columns(share=pl.col("len") / pl.col("len").sum())
        .sort("len", descending=True)
    )
    top = overall.row(0, named=True)
    m.put("f03.top_reason", top["reason"].lower(), "text", **hmda)
    m.put("f03.top_reason_share", top["share"], "pct1", **hmda)
    groups = [RACE_REFERENCE, "Black", "Hispanic or Latino", "Asian"]
    share = {(g, r): s for g, r, s in reasons.select("race_ethnicity_group", "reason", "share").iter_rows()}
    m.put_table(
        "f03.reasons",
        ["Reason for denial", "Denials", "Share", *[f"Share, {g}" for g in groups]],
        ["text", "int", "pct1", *["pct1"] * len(groups)],
        [
            [r["reason"], r["len"], r["share"], *[share.get((g, r["reason"]), 0.0) for g in groups]]
            for r in overall.iter_rows(named=True)
        ],
        **hmda,
    )
    ch_black = share.get(("Black", "Credit history"), 0.0)
    ch_white = share.get((RACE_REFERENCE, "Credit history"), 0.0)
    m.put("f03.credit_history_black", ch_black, "pct1", **hmda)
    m.put("f03.credit_history_white", ch_white, "pct1", **hmda)
    m.put_figure(
        "f03.fig_reasons",
        "The first reason lenders gave for a denial",
        f"{top['reason']} is the most common first reason, on {format_value(top['share'], 'pct1')} of denials. "
        f"Credit history comes first on {format_value(ch_black, 'pct1')} of denials to Black applicants against "
        f"{format_value(ch_white, 'pct1')} for white non Hispanic applicants, and credit history is exactly "
        "what the public file leaves out.",
        data="f03/denial_reasons.parquet",
        **hmda,
    )

    # The proxy list, checked against every model's feature list.
    listed = sorted(protected)
    features = model_feature_lists(ctx.paths.models_dir)
    hits = proxy_hits(features, protected)
    rules_meta: dict[str, Any] = {
        "backend": "static",
        "population": "every model's feature list against rules/proxies.yaml",
        "source": "rules/proxies.yaml",
    }
    m.put("f03.proxy_entries", len(listed), "int", **rules_meta)
    m.put("f03.models_checked", len(features), "int", **rules_meta)
    m.put("f03.models_with_proxies", sum(1 for v in hits.values() if v), "int", **rules_meta)
    m.put_table(
        "f03.proxy_check",
        ["Model", "Features", "Protected attributes or proxies among them"],
        ["text", "int", "text"],
        [[model, len(fs), ", ".join(hits[model]) or "none"] for model, fs in sorted(features.items())],
        **rules_meta,
    )
    m.put("f03.proxy_list", ", ".join(listed), "text", **rules_meta)
    by_year = []
    for year in sorted(frame["year"].unique().to_list()):
        part = frame.filter(pl.col("year") == year)
        t = unadjusted_table(part, "denied", "race_ethnicity_group", RACE_REFERENCE)
        b = t.filter(pl.col("group") == "Black").row(0, named=True)
        by_year.append([year, b["applications"], b["rate"], b["ratio"], b["low"], b["high"]])
    m.put_table(
        "f03.black_by_year",
        ["Year", "Black applicants", "Denial rate", "Ratio to white non Hispanic", "95% low", "95% high"],
        ["text", "int", "pct1", "float2", "float2", "float2"],
        by_year,
        **hmda,
    )


SPEC = FunctionSpec(
    code="f03",
    slug="fair-lending",
    title="Fair lending and adverse action",
    question="Are some applicants denied more often than comparable applicants, and does the scorecard keep "
    "protected attributes out of its decisions and reasons?",
    run=run,
)
