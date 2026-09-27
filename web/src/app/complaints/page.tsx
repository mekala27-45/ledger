import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

export const metadata: Metadata = { title: "Complaints and conduct" };

type Row = Record<string, number | string | null>;

export default function Complaints() {
  const m = manifest();
  const volume = readJson<Row[]>("f07/volume_by_product.json");
  const trend = readJson<Row[]>("f07/topic_trend.json");
  const months = [...new Set(volume.map((r) => String(r.month)))].sort();
  const totals = months.map((mo) => volume.filter((r) => r.month === mo).reduce((a, r) => a + Number(r.complaints), 0));
  const products = [...new Set(volume.map((r) => String(r.product)))];
  const reporting = products.find((p) => p.startsWith("Credit reporting")) ?? "";
  const topicMonths = [...new Set(trend.map((r) => String(r.month)))].sort();
  const topics = [...new Set(trend.map((r) => Number(r.topic)))].sort((a, b) => a - b);
  const labelOf = (t: number) => String(trend.find((r) => Number(r.topic) === t)?.topic_label ?? t);
  return (
    <>
      <PageHeader
        kicker="Function 7 · complaints and conduct · real CFPB data"
        question="What are consumers complaining about, which companies resolve complaints with money, and which issues will cost relief?"
        answer={
          <p>
            The Consumer Financial Protection Bureau received {m.v("f07.complaints")} complaints in two years, and{" "}
            {m.v("f07.top_product_share")} were about credit reports. In the narratives, {m.v("f07.template_share")} are form
            letters; counted once, the topics a reader expects all emerge. Whether a complaint ends in a refund is predicted
            almost as well from the form as from the consumer&apos;s own words, so the relief model that reads the narrative
            is not approved. The Bureau states its database is &ldquo;{m.v("f07.caveat")}&rdquo;, and every figure here carries
            that.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Complaints, two years" value={m.v("f07.complaints")} note={`${m.v("f07.growth")} from the first month to the last`} />
        <Kpi label="Narratives that are form letters" value={m.v("f07.template_share")} note={`Of ${m.v("f07.narratives")} sampled`} />
        <Kpi label="Ended in monetary relief" value={m.v("f07.relief_rate")} note={`${m.v("f07.relief_rate_first")} at the start, ${m.v("f07.relief_rate_last")} at the end`} />
        <Kpi label="Relief model, test AUROC" value={m.v("f07.relief_test_auroc")} note={`Form alone ${m.v("f07.relief_metadata_auroc")}: ${m.v("f07.relief_conclusion")}`} />
      </div>
      <Grid>
        <ChartFrame
          title={m.figure("f07.fig_volume").title}
          callout={m.figure("f07.fig_volume").callout}
          label={m.label("f07.fig_volume")}
          table={m.table("f07.products")}
        >
          <LineChart
            series={[
              { name: "All complaints", points: months.map((mo, i) => ({ x: mo, y: totals[i] ?? 0 })), emphasis: true },
              {
                name: "Credit reports",
                points: months.map((mo) => ({ x: mo, y: Number(volume.find((r) => r.month === mo && r.product === reporting)?.complaints ?? 0) })),
              },
              {
                name: "Everything else",
                points: months.map((mo, i) => ({
                  x: mo,
                  y: (totals[i] ?? 0) - Number(volume.find((r) => r.month === mo && r.product === reporting)?.complaints ?? 0),
                })),
              },
            ]}
            yFormat="int"
            xLabel="Month received"
            yLabel="Complaints"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f07.fig_topics").title}
          callout={m.figure("f07.fig_topics").callout}
          label={m.label("f07.fig_topics")}
          table={m.table("f07.topics")}
        >
          <LineChart
            series={topics.map((t) => ({
              name: `${t + 1}: ${labelOf(t)}`,
              points: topicMonths.map((mo) => ({ x: mo, y: Number(trend.find((r) => r.month === mo && Number(r.topic) === t)?.share ?? 0) })),
            }))}
            yFormat="pct0"
            xLabel="Month received"
            yLabel="Share of sampled narratives"
          />
        </ChartFrame>
      </Grid>

      <Grid>
        <section aria-label="Topics" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">The topics, and whether the expected ones emerged</h3>
          <DataTable table={m.table("f07.expected")} />
          <h3 className="text-sm font-semibold text-ink mt-5 mb-3">Three excerpts per topic</h3>
          <DataTable table={m.table("f07.examples")} max={30} />
          <p className="text-xs text-ink2 mt-2">
            Excerpts are the Bureau&apos;s published narratives, with its redactions and any long number masked.{" "}
            {m.label("f07.topics")}
          </p>
        </section>
        <section aria-label="Company responses" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">How companies closed the sampled complaints</h3>
          <DataTable table={m.table("f07.responses")} />
          <h3 className="text-sm font-semibold text-ink mt-5 mb-3">{m.figure("f07.fig_issues").title}</h3>
          <p className="text-sm mb-3">{m.figure("f07.fig_issues").callout}</p>
          <DataTable table={m.table("f07.issues")} />
          <p className="text-xs text-ink2 mt-2">
            {m.label("f07.fig_issues")} The model&apos;s report is on the{" "}
            <Link className="underline" href="/models/relief/">
              relief validation page
            </Link>
            .
          </p>
        </section>
      </Grid>

      <section aria-label="Company benchmark" className="mt-10">
        <h2 className="font-serif text-2xl mb-1">{m.figure("f07.fig_benchmark").title}</h2>
        <p className="text-sm mb-3 max-w-3xl">{m.figure("f07.fig_benchmark").callout}</p>
        <DataTable table={m.table("f07.benchmark")} />
        <p className="text-xs text-ink2 mt-2">
          {m.label("f07.fig_benchmark")} Real companies, real public data, exactly as the Bureau publishes it. The Bureau
          states its database is &ldquo;{m.v("f07.caveat")}&rdquo;.
        </p>
      </section>

      <Limitations
        items={[
          `The Bureau's database is ${m.v("f07.caveat")}. People who complain, and who write a narrative, are not typical customers.`,
          "Narratives are sampled at about two thousand a month by a hash of the complaint id; the most recent month is thin because the Bureau publishes a narrative only after the company responds and the consumer consents.",
          "The relief model reads real consumers' words. It is not approved: it added too little over the form to justify that, and a transformer, which would read the narratives better, needs model weights this build could not reach.",
        ]}
      />
      <Examiner>
        An examiner would ask what the bank does with a model like the relief model and what it must never do. It is for
        routing complaints to the team that can fix the cause and for ranking issues by the relief they are likely to cost.
        It never decides whether a consumer gets relief and never ranks consumers. Words that name a protected basis are kept
        out of its vocabulary, the Bureau&apos;s tags for older Americans and servicemembers are used only to audit it, and it
        stays unapproved until the narrative earns its place over the form.
      </Examiner>
    </>
  );
}
