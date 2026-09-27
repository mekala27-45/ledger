import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";
import { formatValue } from "@/lib/format";

import { NetworkGraph } from "./NetworkGraph";

export const metadata: Metadata = { title: "Financial crime" };

type Row = Record<string, number | string | boolean | null>;

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const NAMES: Record<string, string> = {
  structuring: "Structuring",
  rapid_movement: "Rapid movement",
  mule: "Mule fan in",
  round_tripping: "Round tripping",
};

export default function Crime() {
  const m = manifest();
  const monthly = readJson<Row[]>("f05/alerts_monthly.json");
  const queue = readJson<Row[]>("f05/queue.json");
  const months = [...new Set(monthly.map((r) => String(r.month)))].sort();
  const series = Object.keys(NAMES).map((rule) => ({
    name: NAMES[rule] ?? rule,
    points: months.map((mo) => ({ x: mo, y: Number(monthly.find((r) => r.month === mo && r.rule === rule)?.alerts ?? 0) })),
  }));
  return (
    <>
      <PageHeader
        kicker="Function 5 · financial crime"
        question="Do the monitoring rules find the planted typologies, and which alert should an investigator open first?"
        answer={
          <p>
            Four rules at the reporting threshold&apos;s boundary fired {m.v("f05.alerts")} alerts over three years,{" "}
            {m.v("f05.per_100k")} per hundred thousand ledger entries, and found {m.v("f05.episodes_found")} of the{" "}
            {m.v("f05.episodes")} complete planted episodes. Structuring carries the workload: cash intensive businesses make
            {" "}{m.v("f05.structuring_alerts")} of its alerts and only {m.v("f05.structuring_precision")} are real. The triage
            model orders the queue, and in the last two months every real alert sits above every lookalike. Nothing here is
            a suspicious activity finding, and no report is filed anywhere.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Alerts, all rules" value={m.v("f05.alerts")} note={`About ${m.v("f05.alerts_per_month")} a month`} />
        <Kpi label="Planted episodes found" value={`${m.v("f05.episodes_found")} of ${m.v("f05.episodes")}`} note={`Recall ${m.v("f05.recall")}`} />
        <Kpi label="Structuring alerts that are real" value={m.v("f05.structuring_precision")} note={`Recall ${m.v("f05.structuring_recall")}`} />
        <Kpi label="Triage AUROC, test months" value={m.v("f05.triage_auroc")} note="A property of the generator; see the report" />
      </div>

      <section className="mb-10" aria-label="The network">
        <h2 className="font-serif text-2xl mb-1">{m.figure("f05.fig_network").title}</h2>
        <p className="text-sm mb-3 max-w-3xl">{m.figure("f05.fig_network").callout}</p>
        <NetworkGraph base={BASE} />
        <p className="text-xs text-ink2 mt-2">{m.label("f05.fig_network")}</p>
      </section>

      <Grid>
        <ChartFrame
          title={m.figure("f05.fig_scorecard").title}
          callout={m.figure("f05.fig_scorecard").callout}
          label={m.label("f05.fig_scorecard")}
          table={m.table("f05.scorecard")}
        >
          <DataTable table={m.table("f05.scorecard")} />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f05.fig_volume").title}
          callout={m.figure("f05.fig_volume").callout}
          label={m.label("f05.fig_volume")}
          table={{
            columns: ["Month", "Rule", "Alerts", "Real"],
            formats: ["text", "text", "int", "int"],
            rows: monthly.map((r) => [String(r.month), NAMES[String(r.rule)] ?? String(r.rule), Number(r.alerts), Number(r.true_alerts)]),
          }}
        >
          <LineChart series={series} yFormat="int" xLabel="Month the alert closed" yLabel="Alerts" />
        </ChartFrame>
      </Grid>

      <section className="mt-10" aria-label="The case queue">
        <h2 className="font-serif text-2xl mb-1">The case queue, {m.v("f05.queue_month")}</h2>
        <p className="text-sm mb-3 max-w-3xl">
          {m.v("f05.queue_alerts")} alerts in the order the{" "}
          <Link className="underline" href="/models/aml_triage/">
            triage model
          </Link>{" "}
          sets. The last column is the generator&apos;s truth, which an investigator would never see; it is here so you can
          check the order.
        </p>
        <div className="overflow-x-auto border border-hairline bg-raised rounded-md p-3">
          <table className="data-table w-full" data-testid="case-queue">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Rule</th>
                <th>Account</th>
                <th>Closed</th>
                <th className="num">Amount</th>
                <th className="num">Triage</th>
                <th>What fired</th>
                <th>Truth</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((q) => (
                <tr key={String(q.alert_id)}>
                  <td className="num">{String(q.position)}</td>
                  <td>{NAMES[String(q.rule)] ?? String(q.rule)}</td>
                  <td className="font-mono text-[11px]">{String(q.account_id)}</td>
                  <td className="whitespace-nowrap">{String(q.end_at).slice(0, 10)}</td>
                  <td className="num">{formatValue(Number(q.amount), "usd0")}</td>
                  <td className="num">{formatValue(Number(q.triage), "float3")}</td>
                  <td className="text-[12px]">{String(q.statement)}</td>
                  <td className={q.true_positive ? "text-critical" : "text-ink2"}>{q.true_positive ? "▲ planted" : "lookalike"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-10" aria-label="Communities">
        <h2 className="font-serif text-2xl mb-2">The communities with planted accounts</h2>
        <DataTable table={m.table("f05.communities_table")} />
        <p className="text-xs text-ink2 mt-2">{m.label("f05.communities_table")}</p>
      </section>

      <Limitations
        items={[
          "The typologies and their lookalikes are generated, and the rules are graded against the generator's truth. A real program learns from investigator dispositions, which are noisier and arrive weeks later.",
          `Three of the four rules fired no false alerts here. The generator's lookalikes for rapid movement and mule fan in do not look enough like the real thing, which a real program's rules would not be so lucky with.`,
          `Recall counts only episodes whose every entry posted; ${m.v("f05.partial_episodes")} round trips posted with a hop missing and are counted beside it.`,
          "Cases on this page are a ranked list. The API opens, updates and audits cases for the fraud desk's alerts; monitoring alerts are not wired into it.",
        ]}
      />
      <Examiner>
        An examiner would ask how the thresholds were set, how many alerts go unworked, and whether the triage model could
        bury a real case. The thresholds are the regulation&apos;s own reporting threshold and stated windows in the
        configuration; every alert stays in the queue, the model only orders it; and its validation report states plainly that
        its separation here comes from the generator and that it would be refit on investigator dispositions before any real
        use.
      </Examiner>
    </>
  );
}
