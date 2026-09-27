import type { Metadata } from "next";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { Diverging } from "@/components/charts/Diverging";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

export const metadata: Metadata = { title: "Treasury and stress testing" };

type Row = Record<string, number | string | null>;

const SCENARIOS = ["Baseline", "Severely adverse"];

export default function Treasury() {
  const m = manifest();
  const shocks = readJson<Row[]>("f08/nii_shocks.json");
  const paths = readJson<Row[]>("f08/stress_paths.json");
  const series = (key: string, low: string, high: string) =>
    SCENARIOS.map((name, i) => {
      const rows = paths.filter((r) => r.scenario === name).sort((a, b) => Number(a.step) - Number(b.step));
      return {
        name,
        emphasis: i === 1,
        points: rows.map((r) => ({ x: `Q${String(r.step)}`, y: Number(r[key]) })),
        band: rows.map((r) => ({ x: `Q${String(r.step)}`, low: Number(r[low]), high: Number(r[high]) })),
      };
    });
  return (
    <>
      <PageHeader
        kicker="Function 8 · treasury and stress testing · the Federal Reserve's 2026 scenarios"
        question="What does a rate move do to earnings, what would a severe recession do to losses and capital, and how long would liquid assets last?"
        answer={
          <p>
            Over twelve months the balance sheet is {m.v("f08.stance")}: a two point rise changes net interest income by{" "}
            {m.v("f08.nii_up200")} and a two point fall by {m.v("f08.nii_down200")}, against {m.v("f08.base_nii")} earned
            over the last year. Along the Federal Reserve&apos;s severely adverse scenario, unemployment at the bank peaks at{" "}
            {m.v("f08.severe_peak_unemployment")} and nine quarters of losses come to {m.v("f08.severe_loss")} (
            {m.v("f08.severe_loss_low")} to {m.v("f08.severe_loss_high")}), which pre provision revenue absorbs. These are
            illustrative projections on a fictional bank in the shape of the supervisory exercise, not the exercise.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Net interest income, +200 bp" value={m.v("f08.nii_up200")} note={`${m.v("f08.nii_up200_share")} of the last twelve months`} />
        <Kpi label="Net interest income, -200 bp" value={m.v("f08.nii_down200")} note={`${m.v("f08.nii_down200_share")} of the last twelve months`} />
        <Kpi label="Severely adverse losses, nine quarters" value={m.v("f08.severe_loss")} note={`${m.v("f08.severe_loss_rate")} of loans`} />
        <Kpi label="Liquidity coverage, simplified" value={m.v("f08.lcr")} note={`${m.v("f08.lcr_concentration")} if the top 1% of depositors leave`} />
      </div>
      <Grid>
        <ChartFrame
          title={m.figure("f08.fig_nii").title}
          callout={m.figure("f08.fig_nii").callout}
          label={m.label("f08.fig_nii")}
          table={m.table("f08.nii_table")}
        >
          <Diverging
            fmt="usd0"
            zeroLabel="No change"
            items={[...shocks]
              .sort((a, b) => Number(b.shock_bps) - Number(a.shock_bps))
              .map((r) => ({
                label: `${Number(r.shock_bps) > 0 ? "+" : ""}${String(r.shock_bps)} bp`,
                value: Number(r.nii_change),
                note: "Change in net interest income over twelve months",
              }))}
          />
        </ChartFrame>
        <section aria-label="Repricing" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">What reprices within the year</h3>
          <DataTable table={m.table("f08.repricing")} />
          <p className="text-sm text-ink2 mt-3">
            Deposit betas come from the deposits function. Installment loans and mortgages reprice only as they run off (
            {m.v("f08.installment_runoff")} and {m.v("f08.mortgage_runoff")} of the book over the last year), securities are
            taken as an even {m.v("f08.securities_ladder_years")} year ladder, and {m.v("f08.cd_share_in_year")} of certificates
            mature within the year.
          </p>
        </section>
        <ChartFrame
          title={m.figure("f08.fig_roll").title}
          callout={m.figure("f08.fig_roll").callout}
          label={m.label("f08.fig_roll")}
          table={{
            columns: ["Scenario", "Quarter", "Scenario quarter", "Unemployment, bank", "Roll rate", "Low", "High", "Losses"],
            formats: ["text", "int", "text", "float2", "pct2", "pct2", "pct2", "usd0"],
            rows: paths.map((r) => [r.scenario, r.step, r.scenario_quarter, r.unemployment, r.roll_rate, r.roll_low, r.roll_high, r.loss]),
          }}
        >
          <LineChart series={series("roll_rate", "roll_low", "roll_high")} yFormat="pct1" xLabel="Quarter of the projection" yLabel="Unsecured loans rolling 30 days past due" />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f08.fig_capital").title}
          callout={m.figure("f08.fig_capital").callout}
          label={m.label("f08.fig_capital")}
          table={{
            columns: ["Scenario", "Quarter", "Pre provision revenue", "Losses", "Capital ratio", "Low", "High"],
            formats: ["text", "int", "usd0", "usd0", "pct1", "pct1", "pct1"],
            rows: paths.map((r) => [r.scenario, r.step, r.ppnr, r.loss, r.capital_ratio, r.capital_low, r.capital_high]),
          }}
        >
          <LineChart series={series("capital_ratio", "capital_low", "capital_high")} yFormat="pct0" xLabel="Quarter of the projection" yLabel="Equity over risk weighted assets" />
        </ChartFrame>
      </Grid>

      <Grid>
        <section aria-label="Scenarios" className="border border-hairline bg-raised rounded-md p-4 xl:col-span-2">
          <h3 className="text-sm font-semibold text-ink mb-3">The two scenarios over {m.v("f08.quarters")} quarters</h3>
          <DataTable table={m.table("f08.scenario_table")} />
          <p className="text-xs text-ink2 mt-2">{m.label("f08.scenario_table")}</p>
        </section>
        <section aria-label="The macro link" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">The macro link, and whether it recovers the generator</h3>
          <DataTable table={m.table("f08.link_table")} />
          <p className="text-sm text-ink2 mt-3">
            Fitted on {m.v("f08.link_loan_months")} loan months with {m.v("f08.link_rolls")} rolls into delinquency. The
            generator&apos;s stated sensitivity is {m.v("f08.link_stated")} per point of unemployment; the link recovers{" "}
            {m.v("f08.link_unemployment")} ({m.v("f08.link_unemployment_low")} to {m.v("f08.link_unemployment_high")}), within
            the stated tolerance of {m.v("f08.link_tolerance")} but attenuated, because a bank never sees the latent risk
            score the generator uses. House prices carry no weight in the generator, and the fit gives them almost none.
          </p>
        </section>
        <section aria-label="Liquidity" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">Liquidity coverage, simplified</h3>
          <DataTable table={m.table("f08.liquidity")} />
          <p className="text-sm text-ink2 mt-3">
            High quality liquid assets over thirty day outflows at the stated run rates: {m.v("f08.lcr")}. If the largest one
            percent of depositors, who hold {m.v("f08.top1_balances")}, also left in full, {m.v("f08.lcr_concentration")}. Not
            the regulatory ratio: no inflows, no level two haircuts, no committed lines.
          </p>
        </section>
      </Grid>

      <Limitations
        items={[
          "The balance sheet is held flat and customers do not change behaviour with rates. Real deposit outflows and prepayments move with a shock, and economic value of equity is not measured here.",
          `The link is fitted on ${m.v("f08.link_loan_months")} loan months from a three year history with one recession quarter. It is short, and the generator's macro sensitivity is a stated parameter the fit had to recover before any scenario was projected.`,
          "The scenarios are the Federal Reserve's, applied as changes from their jump off quarter to the bank's own starting unemployment. Mortgage losses are held at their last year's rate; no tax, dividends or growth are modelled.",
        ]}
      />
      <Examiner>
        An examiner would ask where the betas and the macro sensitivity come from and what the bank would do if the ratio
        fell. The betas are recovered from the bank&apos;s own rate sheet and the interest it paid; the macro sensitivity is
        fitted, checked against the generator&apos;s stated value, and carried with its interval into every projection. The
        capital path counts pre provision revenue at its last twelve months and moves it with the scenario&apos;s short rate,
        which is the simplification an examiner would challenge first.
      </Examiner>
    </>
  );
}
