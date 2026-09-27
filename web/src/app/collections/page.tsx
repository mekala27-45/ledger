import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

export const metadata: Metadata = { title: "Collections and recovery" };

type Row = Record<string, number | string | null>;

const PRODUCTS: [string, string][] = [
  ["installment", "Installment"],
  ["card", "Card"],
  ["mortgage", "Mortgage"],
];

export default function Collections() {
  const m = manifest();
  const backtest = readJson<Row[]>("f09/backtest.json");
  const forecast = readJson<Row[]>("f09/forecast.json");
  const recoveries = readJson<Row[]>("f09/recoveries.json");
  return (
    <>
      <PageHeader
        kicker="Function 9 · collections and recovery"
        question="How many loans will charge off in the next six months, whom should a collector call first, and how much comes back?"
        answer={
          <p>
            The roll rate chain expects about {m.v("f09.forecast_charge_offs")} charge offs from {m.v("f09.forecast_first")} to{" "}
            {m.v("f09.forecast_last")}; over {m.v("f09.origins")} backtest origins it missed by {m.v("f09.mape_flat")} on average,
            against {m.v("f09.mape_naive")} for repeating the last six months. {m.v("f09.delinquent_now")} loans are past due
            today, and the first {m.v("f09.queue_size")} calls in the cure model&apos;s queue cover{" "}
            {m.v("f09.queue_exposure")} of the {m.v("f09.total_exposure")} likely to be lost without one. Two years after a
            charge off, installment loans return {m.v("f09.recovery_24_installment")}.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Charge offs expected, next six months" value={m.v("f09.forecast_charge_offs")} note="Installment and card, loans open today" />
        <Kpi label="Backtest error, roll rates" value={m.v("f09.mape_flat")} note={`Naive ${m.v("f09.mape_naive")}`} />
        <Kpi label="Cure model, test AUROC" value={m.v("models.cure.test.auroc")} note={`The bucket rule: ${m.v("models.cure.rule_auroc")}`} />
        <Kpi label="Loss given default, installment" value={m.v("f09.lgd_installment")} note="One minus recoveries at two years" />
      </div>
      <Grid>
        <ChartFrame
          title={m.figure("f09.fig_backtest").title}
          callout={m.figure("f09.fig_backtest").callout}
          label={m.label("f09.fig_backtest")}
          table={{
            columns: ["Origin", "Actual", "Roll rates", "Roll rates, seasonal", "Naive", "Seasonal naive"],
            formats: ["text", "int", "int", "int", "int", "int"],
            rows: backtest.map((r) => [r.origin, r.actual, r.forecast_unadjusted, r.forecast, r.naive, r.seasonal_naive]),
          }}
        >
          <LineChart
            series={[
              { name: "Actual", points: backtest.map((r) => ({ x: String(r.origin), y: Number(r.actual) })), emphasis: true },
              { name: "Roll rates", points: backtest.map((r) => ({ x: String(r.origin), y: Number(r.forecast_unadjusted) })) },
              { name: "Naive", points: backtest.map((r) => ({ x: String(r.origin), y: Number(r.naive) })) },
              { name: "Seasonal naive", points: backtest.map((r) => ({ x: String(r.origin), y: Number(r.seasonal_naive) })) },
            ]}
            yFormat="int"
            xLabel="Forecast origin"
            yLabel="Charge offs in the next six months"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f09.fig_forecast").title}
          callout={m.figure("f09.fig_forecast").callout}
          label={m.label("f09.fig_forecast")}
          table={m.table("f09.forecast_table")}
        >
          <LineChart
            series={[
              { name: "30 days", points: forecast.map((r) => ({ x: String(r.month), y: Number(r.b_30) })) },
              { name: "60 days", points: forecast.map((r) => ({ x: String(r.month), y: Number(r.b_60) })) },
              { name: "90 days and over", points: forecast.map((r) => ({ x: String(r.month), y: Number(r["b_90+"]) })) },
              { name: "Charge offs", points: forecast.map((r) => ({ x: String(r.month), y: Number(r.charge_offs) })), emphasis: true },
            ]}
            yFormat="int"
            xLabel="Month"
            yLabel="Loans"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f09.fig_recovery").title}
          callout={m.figure("f09.fig_recovery").callout}
          label={m.label("f09.fig_recovery")}
          table={{
            columns: ["Product", "Months since charge off", "Recovered, cumulative"],
            formats: ["text", "int", "pct1"],
            rows: recoveries.map((r) => [r.product, r.months_since, r.recovery_rate]),
          }}
        >
          <LineChart
            series={PRODUCTS.map(([key, name], i) => ({
              name,
              emphasis: i === 0,
              points: recoveries.filter((r) => r.product === key).map((r) => ({ x: Number(r.months_since), y: Number(r.recovery_rate) })),
            }))}
            yFormat="pct0"
            yDomain={[0, 1]}
            xLabel="Months since charge off"
            yLabel="Share of the charged off balance recovered"
          />
        </ChartFrame>
        <section aria-label="Backtest and cure rates" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">How the forecast methods did</h3>
          <DataTable table={m.table("f09.backtest_table")} />
          <h3 className="text-sm font-semibold text-ink mt-5 mb-3">Monthly cure rates, stated and observed</h3>
          <DataTable table={m.table("f09.cure_rates")} />
          <p className="text-sm text-ink2 mt-3">
            The generator states each bucket&apos;s cure rate for a loan of average risk. Riskier loans are late more often and
            cure less, so the observed rates sit below the stated ones.
          </p>
        </section>
      </Grid>

      <section aria-label="The collections queue" className="mt-10">
        <h2 className="font-serif text-2xl mb-1">{m.figure("f09.fig_queue").title}</h2>
        <p className="text-sm mb-3 max-w-3xl">{m.figure("f09.fig_queue").callout}</p>
        <DataTable table={m.table("f09.queue_top")} />
        <p className="text-xs text-ink2 mt-2">
          {m.label("f09.fig_queue")} The model and its gates are in the{" "}
          <Link className="underline" href="/models/cure/">
            cure validation report
          </Link>
          .
        </p>
      </section>

      <Limitations
        items={[
          "The book is generated. Its delinquency follows a stated process with no calendar season, which is why the seasonal adjustment could not help.",
          "The forecast holds the last six months' transitions and adds no new loans. A change in underwriting or the economy breaks the first assumption at once.",
          "Recoveries are observed for two years after charge off; anything collected later is not in the loss given default.",
        ]}
      />
      <Examiner>
        An examiner would ask how the charge off forecast is checked and why the queue is in this order. The forecast is
        backtested on rolling origins against naive and seasonal naive benchmarks and published whichever way it came out;
        the queue is ordered by balance times the chance of not curing, and the cure model had to beat the bucket rule
        collectors use today before it could set that order.
      </Examiner>
    </>
  );
}
