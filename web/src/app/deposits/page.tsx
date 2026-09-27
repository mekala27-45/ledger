import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

export const metadata: Metadata = { title: "Deposits and customers" };

type Row = Record<string, number | string | null>;

const PRODUCTS: [string, string][] = [
  ["checking", "Checking"],
  ["savings", "Savings"],
  ["time", "Time deposits"],
];

export default function Deposits() {
  const m = manifest();
  const monthly = readJson<Row[]>("f06/deposits_monthly.json");
  const rates = readJson<Row[]>("f06/rates.json");
  const months = [...new Set(monthly.map((r) => String(r.month)))].sort();
  const at = (product: string, month: string, key: string) =>
    Number(monthly.find((r) => r.product === product && r.month === month)?.[key] ?? 0);
  return (
    <>
      <PageHeader
        kicker="Function 6 · deposits and customers"
        question="Where are the deposits, how much of a rate cut reaches customers, and whom should the bank call before they leave?"
        answer={
          <p>
            Deposits stand at {m.v("f06.deposits")}, {m.v("f06.growth")} over three years, and the largest one percent of
            depositors hold {m.v("f06.top1_share")} of them. When the policy rate fell {m.v("f06.policy_cut")} points, savings
            passed on {m.v("f06.paid_beta_savings")} of the cut at once, while time deposits passed on{" "}
            {m.v("f06.paid_beta_year_time")} in the first year because a certificate reprices only when it matures. The
            retention list puts {m.v("f06.list_expected_balance")} of expected balance at risk in front of{" "}
            {m.v("f06.list_size")} calls.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Deposits" value={m.v("f06.deposits")} note={`Checking ${m.v("f06.checking_share")} of the total`} />
        <Kpi label="Held by the top 1% of depositors" value={m.v("f06.top1_share")} note={`Top 10% hold ${m.v("f06.top10_share")}`} />
        <Kpi label="Deposit betas recovered" value={`${m.v("f06.betas_recovered")} of 3`} note={`Within ${m.v("f06.beta_tolerance")} of the generator's`} />
        <Kpi label="Attrition model, test AUROC" value={m.v("models.attrition.test.auroc")} note={`Ceiling ${m.v("models.attrition.ceiling")}: most attrition is chance`} />
      </div>
      <Grid>
        <ChartFrame
          title={m.figure("f06.fig_balances").title}
          callout={m.figure("f06.fig_balances").callout}
          label={m.label("f06.fig_balances")}
          table={{
            columns: ["Month", "Checking", "Savings", "Time deposits"],
            formats: ["text", "usdm", "usdm", "usdm"],
            rows: months.map((mo) => [mo, at("checking", mo, "balance"), at("savings", mo, "balance"), at("time", mo, "balance")]),
          }}
        >
          <LineChart
            series={PRODUCTS.map(([key, name], i) => ({
              name,
              emphasis: i === 0,
              points: months.map((mo) => ({ x: mo, y: at(key, mo, "balance") })),
            }))}
            yFormat="usdm"
            xLabel="Month"
            yLabel="Balance"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f06.fig_rates").title}
          callout={m.figure("f06.fig_rates").callout}
          label={m.label("f06.fig_rates")}
          table={{
            columns: ["Month", "Policy rate", "Savings offered", "Savings paid", "Time offered", "Time paid"],
            formats: ["text", "float2", "float2", "float2", "float2", "float2"],
            rows: rates.map((r) => [r.month, r.policy_rate, r.savings_rate, r.savings, r.time_rate, r.time]),
          }}
        >
          <LineChart
            series={[
              { name: "Policy rate", points: rates.map((r) => ({ x: String(r.month), y: Number(r.policy_rate) })), emphasis: true },
              { name: "Time, offered", legend: "Time deposits", points: rates.map((r) => ({ x: String(r.month), y: Number(r.time_rate) })), dash: "4 3" },
              { name: "Time, paid", legend: "Time deposits", points: rates.map((r) => ({ x: String(r.month), y: Number(r.time) })) },
              { name: "Savings, paid", points: rates.map((r) => ({ x: String(r.month), y: Number(r.savings) })) },
            ]}
            yFormat="float2"
            xLabel="Month"
            yLabel="Rate, percent"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f06.fig_flows").title}
          callout={m.figure("f06.fig_flows").callout}
          label={m.label("f06.fig_flows")}
          table={{
            columns: ["Month", "Opened", "Closed"],
            formats: ["text", "int", "int"],
            rows: months.map((mo) => [mo, at("checking", mo, "opened"), at("checking", mo, "closed")]),
          }}
        >
          <LineChart
            series={[
              { name: "Opened", points: months.map((mo) => ({ x: mo, y: at("checking", mo, "opened") })) },
              { name: "Closed", points: months.map((mo) => ({ x: mo, y: at("checking", mo, "closed") })), emphasis: true },
            ]}
            yFormat="int"
            xLabel="Month"
            yLabel="Checking accounts"
          />
        </ChartFrame>
        <section aria-label="Deposit betas" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">Deposit betas: the generator&apos;s, recovered, and paid</h3>
          <DataTable table={m.table("f06.betas")} />
          <p className="text-sm text-ink2 mt-3">
            The offered rate betas are recovered from the rate sheet over the months no floor binds and checked against the
            generator&apos;s known parameters. The paid rate betas come from interest actually credited, and they are what net
            interest income feels.
          </p>
        </section>
      </Grid>

      <section aria-label="The retention list" className="mt-10">
        <h2 className="font-serif text-2xl mb-1">{m.figure("f06.fig_retention").title}</h2>
        <p className="text-sm mb-3 max-w-3xl">{m.figure("f06.fig_retention").callout}</p>
        <DataTable table={m.table("f06.retention_top")} />
        <p className="text-xs text-ink2 mt-2">
          {m.label("f06.fig_retention")} The model and its gates are in the{" "}
          <Link className="underline" href="/models/attrition/">
            attrition validation report
          </Link>
          .
        </p>
      </section>

      <Grid>
        <section aria-label="Concentration" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">Concentration</h3>
          <DataTable table={m.table("f06.concentration")} />
        </section>
        <section aria-label="Product holding" className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold text-ink mb-3">Product holding</h3>
          <DataTable table={m.table("f06.holding")} />
          <p className="text-sm text-ink2 mt-3">{m.v("f06.products_per_customer")} product types per customer on average.</p>
        </section>
      </Grid>

      <Limitations
        items={[
          "The customers, balances and rate sheet are generated. The betas are recovered from a generator that was written with them, which proves the pipeline, not the betas of any real bank.",
          `The attrition model's AUROC of ${m.v("models.attrition.test.auroc")} is close to the ceiling of ${m.v("models.attrition.ceiling")} that the generator's own hazards reach. A real bank has no ceiling to measure against and should expect less.`,
          "A customer who keeps the checking account open and moves the salary elsewhere has left in every way that matters, and the closure label does not see it.",
        ]}
      />
      <Examiner>
        An examiner would ask what the deposit concentration means for liquidity and how the rate sensitivity was set. The
        largest one percent of depositors hold {m.v("f06.top1_share")} of deposits, and the treasury function&apos;s stress
        outflows are applied to the balance sheet with that in view. The betas treasury uses are the ones recovered here,
        from the rate sheet and from interest actually paid, not assumptions typed into a model.
      </Examiner>
    </>
  );
}
