import Link from "next/link";

import { ChartFrame } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { StripPlot, type Strip } from "@/components/charts/StripPlot";
import { Examiner, Grid, Kpi, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

type Row = Record<string, number | string | null>;

const RATIO_FMT: Record<string, string> = {
  "Net interest margin": "pct2",
  "Efficiency ratio": "pct1",
  "Return on assets": "pct2",
  "Return on equity": "pct1",
  "Nonperforming loans": "pct2",
  "Allowance to loans": "pct2",
  "Capital ratio (simplified)": "pct1",
  "Loans to deposits": "pct1",
};

export default function Glance() {
  const m = manifest();
  const ratios = readJson<Row[]>("f01/ratios_monthly.json");
  const strips = readJson<Row[]>("f01/peer_strips.json");
  const peer = m.table("f01.peer_table");
  const stripData: Strip[] = peer.rows.map((row) => {
    const label = String(row[0]);
    return {
      label,
      fmt: RATIO_FMT[label] ?? "pct1",
      ours: Number(row[1]),
      peers: strips.filter((s) => s.ratio === label).map((s) => Number(s.value)),
    };
  });
  const trend = (key: string, name: string) => ({
    name,
    points: ratios.map((r) => ({ x: String(r.month), y: r[key] as number | null })),
    band: ratios.map((r) => ({ x: String(r.month), low: r[`${key}_low`] as number | null, high: r[`${key}_high`] as number | null })),
  });
  const insights = m.table("f01.insights").rows.slice(0, 3);
  const functions: [string, string, string, string][] = [
    ["/lending/", "Consumer lending", "Expected loss, open installment book", m.v("f02.el_total")],
    ["/desk/", "The fraud desk", "Cost at the operating point, test months", m.v("models.fraud_card.cost_op")],
    ["/models/", "Model risk", "Models in the inventory, each with a validation report", m.v("f10.models")],
    ["/controls/", "Controls", "Ledger account months tied to the cent", `${m.v("f11.account_months_tied")} of ${m.v("f11.account_months")}`],
    ["/studio/", "Scorecard studio", "Scorecard AUROC, out of time", m.v("models.pd_scorecard.test.auroc")],
    ["/report/", "Board pack", "Recommended installment cutoff", m.v("f12.recommended_cutoff")],
  ];
  return (
    <>
      <PageHeader
        kicker="Function 1 · the bank at a glance"
        question="How is the bank doing this quarter, and against whom?"
        answer={
          <p>
            Harborline closed {m.v("f01.peer_quarter")} with {m.v("f01.total_assets")} in assets and a net interest margin
            of {m.v("f01.nim_q")}, above {m.v("f01.peer_nim_percentile")} of {m.v("f01.peer_count")} real banks its size in
            its region, because {m.v("f01.consumer_loan_share")} of its loans are card and consumer installment lending.
            Every figure below is built from a general ledger that reconciles to the cent, with one planted break located.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Total assets" value={m.v("f01.total_assets")} note={`As of ${m.v("f01.as_of_month")}`} />
        <Kpi label="Net income, trailing twelve months" value={m.v("f01.net_income_ttm")} />
        <Kpi label="Net interest margin" value={m.v("f01.nim_q")} note={`Peer median ${m.v("f01.peer_nim_median")}`} />
        <Kpi label="Efficiency ratio" value={m.v("f01.efficiency_ratio_q")} note={`Peer median ${m.v("f01.peer_efficiency_ratio_median")}`} />
        <Kpi label="Gross loans" value={m.v("f01.total_loans")} />
        <Kpi label="Deposits" value={m.v("f01.total_deposits")} />
        <Kpi label="Nonperforming loans" value={m.v("f01.npl_ratio_q")} note={`Peer median ${m.v("f01.peer_npl_ratio_median")}`} />
        <Kpi label="Capital ratio (simplified)" value={m.v("f01.capital_ratio_q")} note="Equity over simplified risk weighted assets" />
      </div>
      <section aria-label="The functions" className="mb-8">
        <h2 className="font-serif text-2xl mb-3">The functions, one number each</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {functions.map(([href, title, what, value]) => (
            <Link key={href} href={href} className="border border-hairline bg-raised rounded-md px-4 py-3 hover:border-accent">
              <div className="text-sm font-semibold">{title}</div>
              <div className="text-xs text-ink2">{what}</div>
              <div className="text-xl num text-left mt-1">{value}</div>
            </Link>
          ))}
        </div>
      </section>
      <Grid>
        <ChartFrame
          title={m.figure("f01.fig_ratios").title}
          callout={m.figure("f01.fig_ratios").callout}
          label={m.label("f01.fig_ratios")}
          table={{
            columns: ["Month", "NIM", "ROA", "NPL ratio"],
            formats: ["text", "pct2", "pct2", "pct2"],
            rows: ratios.map((r) => [r.month, r.nim, r.roa, r.npl_ratio]),
          }}
        >
          <LineChart
            series={[trend("nim", "Net interest margin"), trend("roa", "Return on assets"), trend("npl_ratio", "Nonperforming loans")]}
            yFormat="pct1"
            xLabel="Month"
            yLabel="Ratio"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f01.fig_peers").title}
          callout={m.figure("f01.fig_peers").callout}
          label={m.label("f01.fig_peers")}
          table={peer}
        >
          <StripPlot strips={stripData} oursLabel="Harborline Bank (fictional)" />
        </ChartFrame>
      </Grid>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        <section>
          <h2 className="font-serif text-2xl mb-3">What moved, largest first</h2>
          <ol className="space-y-2 text-sm list-decimal pl-5">
            {insights.map((row) => (
              <li key={String(row[0])}>{String(row[1])}</li>
            ))}
          </ol>
          <p className="text-xs text-ink2 mt-2">
            Written by a rules engine from the metric layer, ranked by dollar materiality. No language model writes a sentence
            about a number here.
          </p>
        </section>
        <section className="border border-hairline bg-raised rounded-md p-4">
          <h2 className="font-serif text-2xl mb-2">Reconciliation status</h2>
          <p className="text-sm">
            <span className="text-good font-semibold">✓ {m.v("f11.account_months_tied")} of {m.v("f11.account_months")}</span>{" "}
            ledger account months tie to the cent. <span className="text-warning font-semibold">⚠ One break</span>: account{" "}
            {m.v("f11.break_account")}, {m.v("f11.break_amount")}, first in {m.v("f11.break_month")}, planted to prove the control
            finds it.
          </p>
          <p className="text-sm mt-2">
            Read the <Link className="underline" href="/report/">board pack</Link> or the{" "}
            <Link className="underline" href="/controls/">controls</Link>.
          </p>
        </section>
      </div>
      <Examiner>
        An examiner would ask whether these ratios tie to the regulatory reports and how the peer group was chosen. The ratios
        tie to the general ledger, not to a Call Report, because Harborline files none. The peer group is the population named
        under the peer chart, taken from the FDIC&apos;s own financial data for the latest quarter, and a bank that did not report
        an item is left out of that item rather than counted as zero.
      </Examiner>
    </>
  );
}
