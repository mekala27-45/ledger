import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { CountyMap } from "@/components/charts/CountyMap";
import { Forest } from "@/components/charts/Forest";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

export const metadata: Metadata = { title: "Fair lending" };

type Row = Record<string, number | string | null>;

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function FairLending() {
  const m = manifest();
  const forest = readJson<Row[]>("f03/forest.json");
  const county = readJson<Row[]>("f03/county.json");
  const order = ["Black", "Not provided", "Hispanic or Latino", "Asian", "Other or joint", "Female", "Joint"];
  const rows = [...forest]
    .sort((a, b) => order.indexOf(String(a.group)) - order.indexOf(String(b.group)))
    .map((r) => ({
      section: `${String(r.dimension)[0]?.toUpperCase()}${String(r.dimension).slice(1)}, against ${String(r.reference)[0]?.toLowerCase()}${String(r.reference).slice(1)} applicants`,
      label: String(r.group),
      a: { value: Number(r.raw_or), low: Number(r.raw_low), high: Number(r.raw_high) },
      b: { value: Number(r.adj_or), low: Number(r.adj_low), high: Number(r.adj_high) },
    }));
  return (
    <div data-theme="light" className="bg-surface text-ink rounded-md px-4 py-6 sm:px-8 sm:py-8 -mx-2 sm:mx-0">
      <PageHeader
        kicker="Function 3 · fair lending and adverse action · real HMDA data"
        question="Are some applicants denied more often than comparable applicants?"
        answer={
          <p>
            In New Jersey&apos;s {m.v("f03.applications")} decided mortgage applications for {m.v("f03.years")}, Black
            applicants were denied at {m.v("f03.black_rate")} against {m.v("f03.white_rate")} for white non Hispanic
            applicants. Holding income, loan size, loan to value, debt to income, loan type and purpose, the underwriting
            system and the lender fixed, the odds ratio falls from {m.v("f03.black_or_raw")} to {m.v("f03.black_or")}. The gap
            narrows and does not close, and the public file has no credit score or underwriting result, so what remains is a
            question to ask of a lender&apos;s own data, not a finding.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Applications with a decision" value={m.v("f03.applications")} note={`${m.v("f03.lenders")} lenders`} />
        <Kpi label="Denial rate, all applicants" value={m.v("f03.denial_rate")} />
        <Kpi label="Black applicants, adjusted odds ratio" value={m.v("f03.black_or")} note={`${m.v("f03.black_or_low")} to ${m.v("f03.black_or_high")}`} />
        <Kpi
          label="Comparisons surviving Benjamini and Hochberg"
          value={`${m.v("f03.significant_adjusted")} of ${m.v("f03.adjusted_comparisons")}`}
          note="Adjusted, at q below 0.05"
        />
      </div>
      <Grid>
        <ChartFrame
          title={m.figure("f03.fig_disparity").title}
          callout={m.figure("f03.fig_disparity").callout}
          label={m.label("f03.fig_disparity")}
          table={m.table("f03.adjusted")}
        >
          <Forest rows={rows} aLabel="Unadjusted odds ratio" bLabel="Adjusted odds ratio" xLabel="Odds of denial against the reference group (log scale; 1 is parity)" />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f03.fig_map").title}
          callout={m.figure("f03.fig_map").callout}
          label={m.label("f03.fig_map")}
          table={m.table("f03.county_table")}
        >
          <CountyMap
            base={BASE}
            counties={county.map((c) => ({
              fips: String(c.county_fips),
              name: String(c.county),
              values: { rate: Number(c.rate), adjusted_rate: Number(c.adjusted_rate) },
            }))}
            measures={[
              { key: "rate", label: "Unadjusted denial rate", fmt: "pct1" },
              { key: "adjusted_rate", label: "Adjusted for the application mix", fmt: "pct1" },
            ]}
            reference={{ label: "State", value: m.num("f03.denial_rate"), fmt: "pct1" }}
          />
        </ChartFrame>
      </Grid>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-10">
        <section aria-label="Unadjusted">
          <h2 className="font-serif text-2xl mb-2">Before adjustment</h2>
          <DataTable table={m.table("f03.unadjusted")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f03.unadjusted")}</p>
        </section>
        <section aria-label="Adjusted">
          <h2 className="font-serif text-2xl mb-2">After adjustment</h2>
          <p className="text-sm mb-2">
            Asian applicants are denied about as often as white non Hispanic applicants before adjustment (a rate ratio of{" "}
            {m.v("f03.asian_ratio")}) and carry an adjusted odds ratio of {m.v("f03.asian_or")}: on the observed controls
            their files are stronger, so equal files are denied more often. Adjustment can widen a gap as well as narrow one.
          </p>
          <DataTable table={m.table("f03.adjusted")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f03.adjusted")}</p>
        </section>
        <section aria-label="Denial reasons">
          <h2 className="font-serif text-2xl mb-2">The reasons lenders gave</h2>
          <p className="text-sm mb-2">{m.figure("f03.fig_reasons").callout}</p>
          <DataTable table={m.table("f03.reasons")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f03.reasons")}</p>
        </section>
        <section aria-label="Proxy list">
          <h2 className="font-serif text-2xl mb-2">The proxy list, and the test that holds every model to it</h2>
          <p className="text-sm mb-2">
            {m.v("f03.proxy_entries")} protected attributes and proxies no credit or fraud model may use: {m.v("f03.proxy_list")}.
            Every published model&apos;s feature list is checked against it in the pipeline and in CI.
          </p>
          <DataTable table={m.table("f03.proxy_check")} />
          <p className="text-sm mt-3">
            The scorecard&apos;s adverse action reasons come from the same discipline: the characteristics furthest below
            their best attainable points, never an entry on this list, and none for an approved applicant. Try it in the{" "}
            <Link className="underline" href="/studio/">
              studio
            </Link>
            .
          </p>
        </section>
      </div>
      <Limitations
        items={[
          "HMDA's public file has no credit score and no automated underwriting result. They are the variables a lender's own analysis controls for first, and their absence is the main reason an adjusted gap here is not a finding.",
          "Race, ethnicity and sex are HMDA's derived fields as applicants reported them. Applicants who did not report are their own group and are denied more often, which a lender's own review would look into.",
          "Lenders with too few applications, or no denials, share one fixed effect; the rest are compared within lender.",
          "Harborline Bank's own mortgage applications are generated, with no real HMDA filing behind them, so the method runs on the real New Jersey register, the data an examiner would start from.",
        ]}
      />
      <Examiner>
        An examiner would ask which comparisons were run, whether the results were corrected for running many of them, and
        what the bank did about a gap that survived adjustment. Every comparison is in the tables above with its Benjamini
        and Hochberg q value; the method, the controls and the proxy list are in{" "}
        <a className="underline" href="https://github.com/mekala27-45/ledger/blob/main/docs/fair-lending.md">
          docs/fair-lending.md
        </a>
        ; and the next step for a real lender would be a file review of matched denied and approved applications, which
        public data cannot support.
      </Examiner>
    </div>
  );
}
