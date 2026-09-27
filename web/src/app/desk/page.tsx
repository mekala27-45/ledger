import type { Metadata } from "next";

import { Bars } from "@/components/charts/Bars";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";

import { DeskClient } from "./DeskClient";

export const metadata: Metadata = { title: "The fraud desk" };

type Row = Record<string, number | string | null>;

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const API = process.env.NEXT_PUBLIC_LEDGER_API ?? "";

export default function Desk() {
  const m = manifest();
  const cost = readJson<Row[]>("f04/cost_curve.json").filter((r) => r.sample === "test");
  const pr = readJson<Row[]>("f04/pr_curve.json");
  const lag = readJson<Row[]>("f04/label_lag.json");
  const op = m.num("f04.operating_point");
  const queue = m.num("f04.queue_point");
  const nearest = (rows: Row[], t: number) =>
    rows.reduce((a, b) => (Math.abs(Number(b.threshold) - t) < Math.abs(Number(a.threshold) - t) ? b : a), rows[0] ?? {});
  const costAtOp = nearest(cost, op);
  // Scores pile up near zero, so thresholds are drawn on a log scale.
  const lg = (v: unknown) => Math.log10(Math.max(Number(v), 1e-6));
  // The card model's audit rows: age bands in order, then gender.
  const audit = m.table("models.fraud_card.subgroups");
  const fprAt = audit.columns.indexOf("Fpr");
  const bandOrder = ["under 25", "25 to 39", "40 to 59", "60 and over", "F", "M"];
  const genderWords: Record<string, string> = { F: "Female", M: "Male" };
  const cardGroups = [...audit.rows]
    .sort((a, b) => bandOrder.indexOf(String(a[0])) - bandOrder.indexOf(String(b[0])))
    .map((r) => ({ label: genderWords[String(r[0])] ?? `Aged ${String(r[0])}`, fpr: Number(r[fprAt]) }));
  const alternatives = m.table("models.fraud_account.alternatives").rows;
  return (
    <>
      <PageHeader
        kicker="Function 4 · the fraud desk"
        question="At what score should the desk decline, and what can it honestly say about its own precision?"
        answer={
          <p>
            The desk declines at {m.v("f04.operating_point")}, the threshold that minimised expected cost on the validation
            months. On the test months that costs {m.v("models.fraud_card.cost_op")} against {m.v("models.fraud_card.cost_all")}{" "}
            for approving everything, a saving of {m.v("models.fraud_card.saving_share")}. Labels arrive late: on the as of
            date {m.v("f04.unlabelled_on_as_of")} of {m.v("f04.decisions_on_as_of")} decisions were still inside the{" "}
            {m.v("policy.chargeback_window_days")} day chargeback window, so the desk reports precision over labelled
            decisions only and says how many it cannot yet judge.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Operating point" value={m.v("f04.operating_point")} note="Chosen on validation months by expected cost" />
        <Kpi label="Queue point" value={m.v("f04.queue_point")} note={`Validation precision floor ${m.v("policy.queue_precision_floor")}`} />
        <Kpi label="Precision at the operating point" value={m.v("models.fraud_card.precision_op")} note="Test months" />
        <Kpi label="Recall at the operating point" value={m.v("models.fraud_card.recall_op")} note="Test months" />
      </div>

      <section aria-label="The desk" className="mb-10">
        <h2 className="font-serif text-2xl mb-1">The desk, as it runs</h2>
        <p className="text-sm text-ink2 mb-4 max-w-3xl">
          The API replays the scored test stream on a simulated clock: an asyncio task reading a file, not a message bus.
          When it is asleep this page plays the same stream, recorded, in your browser, and says so.
        </p>
        <DeskClient
          base={BASE}
          apiUrl={API}
          costFalseDecline={m.num("models.fraud_card.cost_false_decline")}
          costHandling={m.num("models.fraud_card.cost_handling")}
        />
      </section>

      <Grid>
        <ChartFrame
          title={m.figure("f04.fig_cost").title}
          callout={m.figure("f04.fig_cost").callout}
          label={m.label("f04.fig_cost")}
          table={{
            columns: ["Threshold", "False decline cost", "Missed fraud cost", "Total cost", "Flagged"],
            formats: ["float4", "usd0", "usd0", "usd0", "int"],
            rows: cost.map((r) => [r.threshold, r.false_decline_cost, r.missed_fraud_cost, r.total_cost, r.flagged]),
          }}
        >
          <LineChart
            series={[
              { name: "Total", points: cost.map((r) => ({ x: lg(r.threshold), y: Number(r.total_cost) })), emphasis: true },
              { name: "False declines", points: cost.map((r) => ({ x: lg(r.threshold), y: Number(r.false_decline_cost) })) },
              { name: "Missed fraud", points: cost.map((r) => ({ x: lg(r.threshold), y: Number(r.missed_fraud_cost) })) },
            ]}
            markers={[{ x: lg(costAtOp.threshold ?? op), label: "operating point" }]}
            yFormat="usdm"
            xLabel="Decline threshold (score, log scale)"
            yLabel="Expected cost"
            xFormat="log10"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f04.fig_pr").title}
          callout={m.figure("f04.fig_pr").callout}
          label={m.label("f04.fig_pr")}
          table={{
            columns: ["Threshold", "Precision", "Recall", "Flagged"],
            formats: ["float4", "pct1", "pct1", "int"],
            rows: pr.map((r) => [r.threshold, r.precision, r.recall, r.flagged]),
          }}
        >
          <LineChart
            series={[
              { name: "Precision", points: pr.map((r) => ({ x: lg(r.threshold), y: Number(r.precision) })) },
              { name: "Recall", points: pr.map((r) => ({ x: lg(r.threshold), y: Number(r.recall) })) },
            ]}
            markers={[
              { x: lg(op), label: "operating" },
              { x: lg(queue), label: "queue" },
            ]}
            yFormat="pct0"
            yDomain={[0, 1]}
            xLabel="Decline threshold (score, log scale)"
            yLabel="Share"
            xFormat="log10"
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f04.fig_lag").title}
          callout={m.figure("f04.fig_lag").callout}
          label={m.label("f04.fig_lag")}
          table={{
            columns: ["Day", "Decisions", "Labelled", "Unlabelled", "Precision, labelled", "Recall, labelled"],
            formats: ["text", "int", "int", "int", "pct1", "pct1"],
            rows: lag.map((r) => [r.day, r.decisions, r.labelled, r.unlabelled, r.precision_labelled, r.recall_labelled]),
          }}
          wide
        >
          <LineChart
            series={[
              { name: "Labelled", points: lag.map((r) => ({ x: String(r.day), y: Number(r.labelled) })) },
              { name: "Unlabelled", points: lag.map((r) => ({ x: String(r.day), y: Number(r.unlabelled) })), emphasis: true },
            ]}
            yFormat="int"
            xLabel="Day"
            yLabel="Scored decisions"
          />
        </ChartFrame>
      </Grid>

      <section aria-label="The fairness audit" className="mt-10">
        <h2 className="font-serif text-2xl mb-1">The fairness audit</h2>
        <p className="text-sm text-ink2 mb-4 max-w-3xl">
          The card model&apos;s errors by age band and gender, beside application fraud on the BAF suite, which was published
          with its protected attributes kept so this question can be asked. Neither model sees age; both are measured on it.
        </p>
        <Grid>
          <ChartFrame
            title={m.figure("f04.fig_card_fairness").title}
            callout={m.figure("f04.fig_card_fairness").callout}
            label={m.label("f04.fig_card_fairness")}
            table={m.table("models.fraud_card.subgroups")}
          >
            <Bars
              ordinal={false}
              fmt="pct2"
              items={cardGroups.map((g) => ({ label: g.label, value: g.fpr, note: "False positive rate at the operating point" }))}
            />
          </ChartFrame>
          <ChartFrame
            title={m.figure("f04.fig_baf").title}
            callout={m.figure("f04.fig_baf").callout}
            label={m.label("f04.fig_baf")}
            table={m.table("models.fraud_account.variants")}
          >
            <Bars
              ordinal={false}
              fmt="pct2"
              items={[
                { label: "Base, 50 and over", value: m.num("models.fraud_account.fpr_older") },
                { label: "Base, under 50", value: m.num("models.fraud_account.fpr_younger") },
                { label: "Variant II, 50 and over", value: m.num("models.fraud_account.ii_fpr_older") },
                { label: "Variant II, under 50", value: m.num("models.fraud_account.ii_fpr_younger") },
              ].map((d) => ({ ...d, note: "False positive rate at the suite's threshold" }))}
            />
          </ChartFrame>
          <ChartFrame
            title={m.figure("f04.fig_alternatives").title}
            callout={m.figure("f04.fig_alternatives").callout}
            label={m.label("f04.fig_alternatives")}
            table={m.table("models.fraud_account.alternatives")}
            wide
          >
            <LineChart
              series={["Base", "Variant II"].map((variant, i) => ({
                name: variant,
                emphasis: i === 0,
                points: alternatives.filter((r) => r[0] === variant).map((r) => ({ x: Number(r[3]), y: Number(r[6]) })),
              }))}
              points
              yDomain={[0, 1]}
              xFormat="pct0"
              yFormat="float2"
              xLabel="Recall at a five percent false positive rate"
              yLabel="Predictive equality (one is parity)"
            />
          </ChartFrame>
        </Grid>
      </section>

      <Limitations
        items={[
          `The stream is Sparkov's generated card transactions (${m.v("models.fraud_card.test_transactions")} in the test months), not real card traffic. The model's AUROC of ${m.v("models.fraud_card.test.auroc")} is a property of the generator, which makes fraud easier to see than any real desk would find it.`,
          `Cost assumes ${m.v("models.fraud_card.cost_false_decline")} per false decline and each missed fraud's amount plus ${m.v("models.fraud_card.cost_handling")}. Both are stated assumptions in the configuration, not measured costs.`,
          "Labels arrive exactly at the end of the chargeback window for every transaction. Real chargebacks arrive over the window, so a real desk would have some labels earlier.",
          "The live desk is a replay on a simulated clock. The API scores nothing new; it reads the scored test stream and reproduces its timing.",
        ]}
      />
      <Examiner>
        An examiner would ask how the threshold was set and who can move it. It was set on the validation months by expected
        cost at the stated unit costs and is reported only on the test months; the slider above recomputes precision, recall
        and cost in the browser but never changes the operating point, which lives in the configuration and the model&apos;s
        validation report. The queue point is the lowest threshold whose validation precision reaches{" "}
        {m.v("policy.queue_precision_floor")}, because an analyst&apos;s hour is budgeted.
      </Examiner>
    </>
  );
}
