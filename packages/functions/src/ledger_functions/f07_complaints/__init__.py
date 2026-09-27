"""Function 7: complaints and conduct, on the Bureau's real complaint database.

Question: what are consumers complaining about, which companies resolve complaints with
money, what do the narratives say, and which issues are likely to cost relief?

Method: complaint volume by product and month from the Bureau's aggregates; the
distribution of company responses; a benchmark of the thirty companies with the most
complaints (share closed with monetary relief, share answered on time); topics over a
reproducible sample of narratives, NMF over TF-IDF, each named by its top terms with
example excerpts and a monthly trend; and the conduct risk view, issues ranked by the
relief expected on recent complaints. Real public data about real companies, exactly as
the Bureau publishes it. The Bureau states the database is not a statistical sample of
consumers' experiences in the marketplace, and every figure here carries that caveat.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest, Scalar
from ledger_nlp.topics import EXPECTED, distinct, excerpt, expected_topics, fit_topics, templates, topic_frame

from ledger_functions.base import Context, FunctionSpec

TOPICS = 10
CAVEAT = "not a statistical sample of consumers' experiences in the marketplace"


def run(ctx: Context) -> None:
    m = ctx.manifest
    cfg = ctx.config
    staged = ctx.paths.staged / "real"
    agg: dict[str, Any] = {
        "backend": "real:cfpb",
        "population": "Every complaint the Bureau received, September 2024 to August 2026, as it publishes them",
        "source": "CFPB complaint search API aggregates",
    }
    sample: dict[str, Any] = {
        "backend": "real:cfpb",
        "population": "A reproducible sample of about 2,000 complaints with narratives a month, September 2024 to August 2026",
        "source": "CFPB export archive, sampled by a salted hash of the complaint id",
    }
    m.put("f07.caveat", CAVEAT, "text", **agg)

    # Volume by product and month.
    volume = pl.read_parquet(staged / "cfpb_volume_by_product.parquet").sort("month", "product")
    ctx.save("volume_by_product", volume)
    totals = volume.group_by("month").agg(pl.col("complaints").sum()).sort("month")
    first, last = totals.row(0, named=True), totals.row(-1, named=True)
    all_complaints = int(volume["complaints"].sum())
    by_product = (
        volume.group_by("product").agg(pl.col("complaints").sum()).sort("complaints", descending=True)
    )
    top = by_product.row(0, named=True)
    m.put("f07.complaints", all_complaints, "int", **agg)
    m.put("f07.top_product", top["product"], "text", **agg)
    m.put("f07.top_product_share", top["complaints"] / all_complaints, "pct1", **agg)
    m.put("f07.first_month", first["month"], "text", **agg)
    m.put("f07.last_month", last["month"], "text", **agg)
    m.put("f07.first_month_complaints", int(first["complaints"]), "int", **agg)
    m.put("f07.last_month_complaints", int(last["complaints"]), "int", **agg)
    m.put("f07.growth", last["complaints"] / first["complaints"] - 1, "spct1", **agg)
    m.put_figure(
        "f07.fig_volume",
        "Complaints to the Bureau by product and month",
        f"{format_value(all_complaints, 'int')} complaints in two years, {format_value(top['complaints'] / all_complaints, 'pct1')} "
        f"of them about {top['product'].lower()}, and the monthly count went from "
        f"{format_value(int(first['complaints']), 'int')} to {format_value(int(last['complaints']), 'int')}. Real public "
        f"data as the Bureau publishes it, which it states is {CAVEAT}.",
        data="f07/volume_by_product.parquet",
        **agg,
    )
    m.put_table(
        "f07.products",
        ["Product", "Complaints", "Share"],
        ["text", "int", "pct1"],
        [
            [r["product"], r["complaints"], r["complaints"] / all_complaints]
            for r in by_product.iter_rows(named=True)
        ],
        **agg,
    )

    # The company benchmark.
    companies = pl.read_parquet(staged / "cfpb_companies.parquet").with_columns(
        monetary_share=pl.col("monetary_relief") / pl.col("complaints"),
        non_monetary_share=pl.col("non_monetary_relief") / pl.col("complaints"),
        timely_share=pl.col("timely") / pl.col("complaints"),
    )
    ctx.save("companies", companies)
    bench_rows: list[list[Scalar]] = [
        [
            r["company"],
            r["top_product"],
            r["complaints"],
            r["monetary_share"],
            r["non_monetary_share"],
            r["timely_share"],
        ]
        for r in companies.sort("complaints", descending=True).iter_rows(named=True)
    ]
    m.put_table(
        "f07.benchmark",
        [
            "Company",
            "Most complained about product",
            "Complaints",
            "Monetary relief",
            "Other relief",
            "Answered on time",
        ],
        ["text", "text", "int", "pct2", "pct1", "pct1"],
        bench_rows,
        **agg,
    )
    top3 = companies.sort("complaints", descending=True).head(3)
    top3_share = float(top3["complaints"].sum()) / all_complaints
    lenders = companies.filter(~pl.col("top_product").str.starts_with("Credit reporting"))
    best = lenders.sort("monetary_share", descending=True).row(0, named=True)
    m.put("f07.top3_share", top3_share, "pct1", **agg)
    m.put("f07.companies", companies.height, "int", **agg)
    m.put("f07.highest_relief_company", best["company"], "text", **agg)
    m.put("f07.highest_relief_share", best["monetary_share"], "pct1", **agg)
    m.put_figure(
        "f07.fig_benchmark",
        "The thirty companies with the most complaints",
        f"The three consumer reporting agencies received {format_value(top3_share, 'pct1')} of all complaints and "
        "closed almost none with monetary relief, because a credit report is corrected rather than refunded. Among the "
        f"rest, {best['company']} closed the largest share with money, {format_value(best['monetary_share'], 'pct1')}. "
        "Real companies, real public data, exactly as the Bureau publishes it; a count of complaints is not a measure of "
        "how a company treats its customers.",
        data="f07/companies.parquet",
        **agg,
    )

    # The narratives: topics.
    raw = pl.read_parquet(staged / "cfpb_narratives.parquet")
    narratives = raw.filter(pl.col("month") < cfg.calendar.as_of.strftime("%Y-%m"))
    responses = (
        narratives.group_by("company_response_to_consumer")
        .agg(pl.len().alias("complaints"))
        .with_columns(share=pl.col("complaints") / pl.col("complaints").sum())
        .sort("complaints", descending=True)
    )
    m.put_table(
        "f07.responses",
        ["Company response", "Complaints in the sample", "Share"],
        ["text", "int", "pct1"],
        responses.rows(),
        **sample,
    )
    monthly_relief = (
        narratives.group_by("month")
        .agg(pl.len().alias("complaints"), pl.col("monetary_relief").mean().alias("relief_rate"))
        .sort("month")
    )
    ctx.save("relief_by_month", monthly_relief)
    m.put("f07.narratives", narratives.height, "int", **sample)
    m.put("f07.relief_rate", float(narratives["monetary_relief"].mean()), "pct1", **sample)  # type: ignore[arg-type]
    m.put("f07.relief_rate_first", float(monthly_relief["relief_rate"][0]), "pct1", **sample)
    m.put("f07.relief_rate_last", float(monthly_relief["relief_rate"][-1]), "pct1", **sample)
    texts = narratives["consumer_complaint_narrative"].to_list()
    is_template, template_share = templates(texts)
    m.put("f07.template_share", template_share, "pct1", **sample)
    keep = distinct(texts)
    m.put("f07.distinct_narratives", len(keep), "int", **sample)
    # Topics are fitted with each form letter counted once, then every narrative is scored.
    model = fit_topics([texts[i] for i in keep], TOPICS, seed=cfg.seed % 10_000)
    weights = model.transform(texts)
    tagged = topic_frame(
        narratives.select("complaint_id", "month", "product", "consumer_complaint_narrative"), weights
    ).with_columns(template=pl.Series(is_template))
    shares = tagged.group_by("topic").agg(pl.len().alias("complaints")).sort("topic")
    trend = (
        tagged.group_by("month", "topic")
        .agg(pl.len().alias("complaints"))
        .join(tagged.group_by("month").agg(pl.len().alias("total")), on="month")
        .with_columns(share=pl.col("complaints") / pl.col("total"))
        .with_columns(
            topic_label=pl.col("topic").replace_strict(dict(enumerate(model.labels)), return_dtype=pl.Utf8)
        )
        .sort("month", "topic")
    )
    ctx.save("topic_trend", trend)
    example_rows: list[list[Scalar]] = []
    topic_rows: list[list[Scalar]] = []
    template_by_topic = dict(tagged.group_by("topic").agg(pl.col("template").mean()).iter_rows())
    fitted = model.weights
    for t in range(TOPICS):
        n = int(shares.filter(pl.col("topic") == t)["complaints"].sum())
        topic_rows.append(
            [
                t + 1,
                ", ".join(model.terms[t][:8]),
                n,
                n / narratives.height,
                float(template_by_topic.get(t, 0.0)),
            ]
        )
        # Examples from distinct narratives, the strongest in the topic, never a form letter twice.
        for i in np.argsort(-fitted[:, t])[:3]:
            example_rows.append([t + 1, excerpt(texts[keep[int(i)]])])
    m.put_table(
        "f07.topics",
        ["Topic", "Top terms", "Complaints where it leads", "Share", "Of which form letters"],
        ["int", "text", "int", "pct1", "pct0"],
        topic_rows,
        **sample,
    )
    m.put_table("f07.examples", ["Topic", "Excerpt"], ["int", "text"], example_rows, **sample)
    found = expected_topics(model)
    emerged = sum(1 for _, i in found if i is not None)
    m.put_table(
        "f07.expected",
        ["What a reader expects", "Marker words", "Emerged as topic"],
        ["text", "text", "text"],
        [
            [theme, ", ".join(EXPECTED[theme][:5]), str(i + 1) if i is not None else "did not emerge"]
            for theme, i in found
        ],
        **sample,
    )
    m.put("f07.expected_emerged", emerged, "int", **sample)
    m.put("f07.expected_total", len(found), "int", **sample)
    m.put("f07.topics_count", TOPICS, "int", **sample)
    missing = [theme for theme, i in found if i is None]
    m.put_figure(
        "f07.fig_topics",
        "What the narratives are about: topics by month",
        f"{format_value(TOPICS, 'int')} topics from non negative matrix factorisation over TF-IDF of "
        f"{format_value(narratives.height, 'int')} narratives. {emerged} of the {len(found)} themes a reader expects "
        "emerged as topics of their own"
        + (f"; {', '.join(t.lower() for t in missing)} did not, and the page says so." if missing else ".")
        + f" {format_value(template_share, 'pct1')} of narratives open like at least four others, form letters "
        "that were counted once when the topics were fitted."
        + f" The sample is {CAVEAT}, like the database it comes from.",
        data="f07/topic_trend.parquet",
        **sample,
    )

    # The conduct risk view.
    relief = Manifest.load(ctx.paths.models_dir / "relief" / "manifest.json")
    issues = pl.read_parquet(ctx.paths.models_dir / "relief" / "issues.parquet")
    ctx.save("issues", issues)
    for key in ("status", "conclusion", "ranking_source", "narrative_gain", "test.auroc", "metadata_auroc"):
        entry = relief.values[f"models.relief.{key}"]
        m.put(f"f07.relief_{key.replace('.', '_')}", entry.value, entry.fmt, **sample)
    m.put_table(
        "f07.issues",
        [
            "Product",
            "Issue",
            "Complaints, test months",
            "Relief expected",
            "Relief that happened",
            "Expected rate",
        ],
        ["text", "text", "int", "float1", "int", "pct1"],
        issues.head(12).rows(),
        **sample,
    )
    top_issue = issues.row(0, named=True)
    m.put_figure(
        "f07.fig_issues",
        "The conduct risk view: issues ranked by the relief they are likely to cost",
        f"On complaints from the test months, {top_issue['issue'].lower()} ({top_issue['product'].lower()}) is expected "
        f"to end in relief {format_value(top_issue['expected_relief'], 'float1')} times, and did "
        f"{format_value(top_issue['actual_relief'], 'int')} times. The ranking comes from "
        f"{relief.text('models.relief.ranking_source')}, because the narrative added only "
        f"{relief.text('models.relief.narrative_gain')} of AUROC. In a bank this ranking is for routing and root cause, "
        "never for deciding whether a consumer gets relief.",
        data="f07/issues.parquet",
        **sample,
    )


SPEC = FunctionSpec(
    code="f07",
    slug="complaints",
    title="Complaints and conduct",
    question="What are consumers complaining about, which companies resolve complaints with money, and which issues are likely to cost relief?",
    run=run,
)
