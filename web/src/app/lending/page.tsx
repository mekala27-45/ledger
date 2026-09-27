import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart, type Series } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";
import { formatValue } from "@/lib/format";

export const metadata: Metadata = { title: "Consumer lending" };

type Row = Record<string, number | string | null>;

export default function Lending() {
  const m = manifest();
  const vintages = readJson<Row[]>("f02/vintages.json");
  const rolls = readJson<Row[]>("f02/roll_rates.json");
  const survival = readJson<Row[]>("f02/survival_curves.json");
  const overlay = readJson<Row[]>("f02/overlay_by_vintage.json");

  const loose = new Set(String(m.raw("policy.loose_vintages")).split(/,\s*|\s+and\s+/));
  const names = [...new Set(vintages.map((r) => String(r.vintage)))].sort();
  // The story is the loosened vintages, so they carry the colour and every other vintage is
  // drawn in one muted line; hover or the table names each one.
  const vintageSeries: Series[] = names.map((v) => ({
    name: loose.has(v) ? `${v} (loosened)` : v,
    legend: loose.has(v) ? `${v} (loosened)` : "Every other vintage",
    points: vintages
      .filter((r) => r.vintage === v)
      .map((r) => ({ x: Number(r.months_on_book), y: r.cumulative_default_rate as number | null })),
    color: loose.has(v) ? (v === [...loose].sort()[0] ? "var(--cat-3)" : "var(--cat-6)") : "var(--control)",
    dash: loose.has(v) ? (v === [...loose].sort()[0] ? "0" : "6 3") : "0",
    emphasis: loose.has(v),
  }));

  const order = (key: "from" | "to") => {
    const seen = new Map<string, number>();
    for (const r of rolls) seen.set(String(r[`${key}_bucket`]), Number(r[`${key}_order`]));
    return [...seen.entries()].sort((a, b) => a[1] - b[1]).map(([name]) => name);
  };
  const fromBuckets = order("from");
  const toBuckets = order("to");
  const cells = fromBuckets.map((f) =>
    toBuckets.map((t) => {
      const hit = rolls.find((r) => r.from_bucket === f && r.to_bucket === t);
      return hit ? Number(hit.rate) : null;
    }),
  );

  const bands = [...new Set(survival.map((r) => String(r.band)))];
  const survivalSeries: Series[] = bands.map((b) => ({
    name: b,
    points: survival.filter((r) => r.band === b).map((r) => ({ x: Number(r.months), y: Number(r.survival) })),
  }));

  const limits = m.table("f02.limits");
  const breaches = limits.rows.filter((r) => r[3] !== "within").length;
  const champion = "models.pd_scorecard";
  const challenger = "models.pd_challenger";
  const comparison = {
    columns: ["Measure, test months", "Scorecard (champion)", "Monotone GBM (challenger)"],
    formats: ["text", "text", "text"],
    rows: [
      ["AUROC", m.v(`${champion}.test.auroc`), m.v(`${challenger}.test.auroc`)],
      ["Gini", m.v(`${champion}.test.gini`), m.v(`${challenger}.test.gini`)],
      ["KS", m.v(`${champion}.test.ks`), m.v(`${challenger}.test.ks`)],
      ["Brier score", m.v(`${champion}.test.brier`), m.v(`${challenger}.test.brier`)],
      ["Expected calibration error", m.v(`${champion}.test.ece`), m.v(`${challenger}.test.ece`)],
      ["Stability, development to test (PSI)", m.v(`${champion}.psi_dev_test`), m.v(`${challenger}.psi_dev_test`)],
      ["Validation conclusion", m.v(`${champion}.conclusion`), m.v(`${challenger}.conclusion`)],
    ],
  };

  return (
    <>
      <PageHeader
        kicker="Function 2 · consumer lending"
        question="Is the installment book performing as priced, and what does it expect to lose?"
        answer={
          <p>
            Not quite. The two vintages written under the loosened cutoff reached {m.v("f02.loose_12mob")} cumulative default
            by twelve months on book, against {m.v("f02.prior_12mob")} for the vintages before them. Expected loss on the open
            installment book is {m.v("f02.el_total")}, {m.v("f02.el_rate")} of {m.v("f02.ead_total")} exposure, after an
            observed to expected overlay that adds {m.v("f02.el_overlay_build")} because the scorecard under predicts those
            vintages. {breaches === 0 ? "Every portfolio limit is within its threshold." : `${breaches} portfolio limits are breached.`}
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Expected loss, open installment book" value={m.v("f02.el_total")} note={`Before overlay ${m.v("f02.el_raw_total")}`} />
        <Kpi label="Loss given default, installment" value={m.v("f02.lgd_installment")} note="One minus recoveries two years after charge off" />
        <Kpi label="CECL style lifetime loss (simplified)" value={m.v("f02.cecl_total")} note={`${m.v("f02.cecl_multiple")} times twelve month expected loss`} />
        <Kpi label="Current to 30 days, monthly" value={m.v("f02.roll_cur_30")} note={`Cure from 30 days ${m.v("f02.roll_cure30")}`} />
      </div>
      <Grid>
        <ChartFrame
          title={m.figure("f02.fig_vintages").title}
          callout={m.figure("f02.fig_vintages").callout}
          label={m.label("f02.fig_vintages")}
          table={{
            columns: ["Vintage", "Months on book", "Loans", "Cumulative default rate"],
            formats: ["text", "int", "int", "pct2"],
            rows: vintages.map((r) => [r.vintage, r.months_on_book, r.loans, r.cumulative_default_rate]),
          }}
          wide
        >
          <LineChart series={vintageSeries} yFormat="pct0" xLabel="Months on book" yLabel="Cumulative default rate" height={320} />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f02.fig_rolls").title}
          callout={m.figure("f02.fig_rolls").callout}
          label={m.label("f02.fig_rolls")}
          table={{
            columns: ["From", "To", "Loan months", "Rate"],
            formats: ["text", "text", "int", "pct2"],
            rows: rolls.map((r) => [r.from_bucket, r.to_bucket, r.loans, r.rate]),
          }}
        >
          <Heatmap
            rows={fromBuckets.map((b) => b.replace(/_/g, " "))}
            columns={toBuckets.map((b) => b.replace(/_/g, " "))}
            cells={cells}
            fmt="pct1"
            rowLabel="bucket this month"
            columnLabel="Bucket next month"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f02.fig_survival").title}
          callout={m.figure("f02.fig_survival").callout}
          label={m.label("f02.fig_survival")}
          table={{
            columns: ["Score band", "Months", "Not yet defaulted"],
            formats: ["text", "float1", "pct1"],
            rows: survival.map((r) => [r.band, r.months, r.survival]),
          }}
        >
          <LineChart series={survivalSeries} yFormat="pct0" xLabel="Months since origination" yLabel="Share not yet defaulted" />
        </ChartFrame>
      </Grid>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-10">
        <section aria-label="Expected loss">
          <h2 className="font-serif text-2xl mb-2">Expected loss by score band</h2>
          <p className="text-sm mb-2">
            Probability of default from the scorecard with the vintage overlay, loss given default from recoveries two years
            after charge off, exposure as the balance at the as of date.
          </p>
          <DataTable table={m.table("f02.el_table")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f02.el_table")}</p>
        </section>
        <section aria-label="Champion and challenger">
          <h2 className="font-serif text-2xl mb-2">Champion and challenger</h2>
          <p className="text-sm mb-2">
            The challenger ranks {m.v("models.pd_challenger.improvement")} AUROC better and agrees with the scorecard&apos;s
            ranking at {m.v("models.pd_challenger.rank_agreement")}. It was not promoted. A gradient boosted model cannot state
            Regulation B reasons directly, so a decline would be explained by a different model from the one that made it, and
            the gain is smaller than the promotion gate its report states.
          </p>
          <DataTable table={comparison} />
          <p className="text-xs text-ink2 mt-2">
            Both reports: <Link className="underline" href="/models/pd_scorecard/">pd_scorecard</Link> and{" "}
            <Link className="underline" href="/models/pd_challenger/">pd_challenger</Link>.
          </p>
        </section>
        <section aria-label="CECL illustration">
          <h2 className="font-serif text-2xl mb-2">A CECL style illustration, simplified</h2>
          <p className="text-sm mb-2">
            Twelve month default probability with the overlay, stretched to a lifetime by the ratio of cumulative default at
            thirty months to twelve on the vintages old enough to show both ({m.v("f02.cecl_multiple")} times), then scaled by
            a macro factor of {m.v("f02.cecl_macro_factor")} for the supervisory baseline&apos;s average unemployment of{" "}
            {m.v("f02.cecl_baseline_unemployment")}. It is labelled simplified because a real allowance adds qualitative
            factors, reversion and prepayment this does not.
          </p>
          <DataTable table={m.table("f02.cecl_table")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f02.cecl_table")}</p>
        </section>
        <section aria-label="Survival model">
          <h2 className="font-serif text-2xl mb-2">What drives time to default</h2>
          <p className="text-sm mb-2">
            A Cox model on the same loans, concordance {m.v("f02.cox_concordance")}. A proportional hazards p value under
            the usual threshold means that covariate&apos;s effect changes with loan age and its ratio is an average.
          </p>
          <DataTable table={m.table("f02.cox")} />
          <h3 className="text-sm font-semibold mt-4 mb-1">Loans still at risk, by month</h3>
          <DataTable table={m.table("f02.at_risk")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f02.cox")}</p>
        </section>
        <section aria-label="Portfolio limits">
          <h2 className="font-serif text-2xl mb-2">Portfolio limits</h2>
          <table className="data-table w-full" data-testid="limits">
            <thead>
              <tr>
                <th>Limit</th>
                <th className="num">Measured</th>
                <th className="num">Limit</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {limits.rows.map((r) => (
                <tr key={String(r[0])}>
                  <td>{String(r[0])}</td>
                  <td className="num">{formatValue(r[1] ?? null, "pct2")}</td>
                  <td className="num">{formatValue(r[2] ?? null, "pct2")}</td>
                  <td className={r[3] === "within" ? "text-good" : "text-critical font-semibold"}>
                    {r[3] === "within" ? "✓ within" : `✕ ${String(r[3])}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-ink2 mt-2">{m.label("f02.limits")}</p>
        </section>
        <section aria-label="Overlay by vintage">
          <h2 className="font-serif text-2xl mb-2">The overlay, vintage by vintage</h2>
          <p className="text-sm mb-2">
            Observed default over the scorecard&apos;s mean predicted default, by origination quarter. The most recent
            vintages carry {m.v("f02.overlay_recent")}.
          </p>
          <DataTable
            table={{
              columns: ["Vintage", "Observed over expected", "Loans"],
              formats: ["text", "float2", "int"],
              rows: overlay.map((r) => [r.vintage, r.overlay, r.loans]),
            }}
          />
        </section>
      </div>

      <Limitations
        items={[
          "The loan book is generated, with a stated risk structure the pipeline recovers before it is trusted. It is not any real lender's portfolio.",
          `Default is ${m.v("policy.default_dpd")} days past due or charge off. A curve stops where its youngest loan's history ends; nothing is extrapolated past the as of date.`,
          "The CECL figure is an illustration of the method on this book, not an allowance. It has no qualitative factors, no reasonable and supportable forecast period with reversion, and no prepayment model.",
        ]}
      />
      <Examiner>
        An examiner would ask how the loosened vintages were caught and whether the loss estimate reflects them. The vintage
        chart is the early warning because it compares loans at the same age, not the same month; the expected loss above
        carries the observed to expected overlay rather than the raw scorecard probability, and the board pack recommends
        holding the cutoff at {m.v("f12.recommended_cutoff")} on the evidence in its cutoff table.
      </Examiner>
    </>
  );
}
