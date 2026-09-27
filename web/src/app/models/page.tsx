import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Grid, Kpi, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";
import { formatValue } from "@/lib/format";

export const metadata: Metadata = { title: "Model risk" };

type Row = Record<string, number | string | null>;

export interface RegistryEntry {
  model_id: string;
  title: string;
  function: string;
  tier: number;
  role: string;
  status: string;
  conclusion: string;
  last_validated: string;
  owner: string;
  purpose: string;
  auroc_test: number | null;
  conditions: string[];
  monitoring: string[][];
}

export default function Models() {
  const m = manifest();
  const registry = readJson<Record<string, RegistryEntry>>("models/registry.json");
  const psi = readJson<Row[]>("f10/pd_psi_by_quarter.json");
  const weekly = readJson<Row[]>("f10/fraud_weekly.json");
  const csi = m.has("f10.pd_csi") ? m.table("f10.pd_csi") : null;
  const warning = m.num("policy.psi_warning");
  const breach = m.num("policy.psi_breach");
  return (
    <>
      <PageHeader
        kicker="Function 10 · model risk management"
        question="Which models make decisions here, and has each one earned it?"
        answer={
          <p>
            The inventory holds {m.v("f10.models")} models, each with a validation report written in the order SR 11-7
            asks for: purpose, data, conceptual soundness, outcomes analysis, benchmarks, limitations, monitoring and a
            conclusion. The conclusions: approved {m.v("f10.approved")}, approved with conditions{" "}
            {m.v("f10.with_conditions")}, not approved {m.v("f10.not_approved")}. The challenge log holds{" "}
            {m.v("f10.challenge_count")} challenges to the models, each with what it changed.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Models in the inventory" value={m.v("f10.models")} />
        <Kpi label="Worst application PSI" value={m.v("f10.pd_psi_worst")} note={`In ${m.v("f10.pd_psi_worst_quarter")}`} />
        <Kpi label="Worst weekly fraud score PSI" value={m.v("f10.fraud_psi_max")} />
        <Kpi label="Weeks before fraud AUROC could be measured" value={m.v("f10.fraud_weeks_without_labels")} note={`First labelled week ${m.v("f10.fraud_first_labelled_week")}`} />
      </div>

      <section aria-label="Inventory" className="mb-10">
        <h2 className="font-serif text-2xl mb-3">The inventory</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3" data-testid="inventory">
          {Object.values(registry).map((r) => (
            <Link
              key={r.model_id}
              href={`/models/${r.model_id}/`}
              className="border border-hairline bg-raised rounded-md p-4 hover:border-accent block"
            >
              <div className="font-mono text-xs text-ink2">{r.model_id}</div>
              <div className="font-semibold mt-1">{r.title}</div>
              <div className="text-sm text-ink2 mt-1">{r.purpose}</div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mt-3">
                <dt className="text-ink2">Tier</dt>
                <dd>{r.tier}</dd>
                <dt className="text-ink2">Role</dt>
                <dd>{r.role}</dd>
                <dt className="text-ink2">Status</dt>
                <dd>{r.status}</dd>
                <dt className="text-ink2">Test AUROC</dt>
                <dd className="num text-left">{formatValue(r.auroc_test, "float3")}</dd>
                <dt className="text-ink2">Last validated</dt>
                <dd>{r.last_validated}</dd>
                <dt className="text-ink2">Conclusion</dt>
                <dd
                  className={
                    r.conclusion === "approved"
                      ? "text-good font-semibold"
                      : r.conclusion === "not approved"
                        ? "text-critical font-semibold"
                        : "text-warning font-semibold"
                  }
                >
                  {r.conclusion === "approved" ? "✓ " : r.conclusion === "not approved" ? "✕ " : "⚠ "}
                  {r.conclusion}
                </dd>
              </dl>
              {r.conditions.length ? (
                <ul className="text-xs mt-3 list-disc pl-4 text-ink2">
                  {r.conditions.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              ) : null}
              <div className="text-xs underline mt-3">Read the validation report</div>
            </Link>
          ))}
        </div>
      </section>

      <Grid>
        <ChartFrame
          title={m.figure("f10.fig_psi").title}
          callout={m.figure("f10.fig_psi").callout}
          label={m.label("f10.fig_psi")}
          table={{
            columns: ["Quarter", "Applications", "PSI"],
            formats: ["text", "int", "float4"],
            rows: psi.map((r) => [r.quarter, r.applications, r.psi]),
          }}
        >
          <LineChart
            series={[
              { name: "PSI", points: psi.map((r) => ({ x: String(r.quarter), y: Number(r.psi) })), emphasis: true },
              { name: "Warning", points: psi.map((r) => ({ x: String(r.quarter), y: warning })), color: "var(--warning)", dash: "5 4" },
              { name: "Breach", points: psi.map((r) => ({ x: String(r.quarter), y: breach })), color: "var(--critical)", dash: "2 3" },
            ]}
            yFormat="float2"
            xLabel="Application quarter"
            yLabel="Population stability index"
            points
          />
        </ChartFrame>
        <ChartFrame
          title={m.figure("f10.fig_fraud_monitoring").title}
          callout={m.figure("f10.fig_fraud_monitoring").callout}
          label={m.label("f10.fig_fraud_monitoring")}
          table={{
            columns: ["Week", "Transactions", "Score PSI", "Labelled", "AUROC, labelled"],
            formats: ["text", "int", "float4", "int", "float3"],
            rows: weekly.map((r) => [r.week, r.transactions, r.psi, r.labelled_test, r.auroc_labelled]),
          }}
        >
          <LineChart
            series={[{ name: "Score PSI", points: weekly.map((r) => ({ x: String(r.week), y: Number(r.psi) })), emphasis: true }]}
            markers={[{ x: String(m.raw("f10.fraud_first_labelled_week")), label: "first labelled week" }]}
            yFormat="float3"
            xLabel="Week"
            yLabel="Score PSI against validation"
            points
          />
        </ChartFrame>
      </Grid>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-10">
        <section aria-label="Challenges">
          <h2 className="font-serif text-2xl mb-2">The challenge log</h2>
          <p className="text-sm mb-2">Every time a result was questioned, what was found and what changed because of it.</p>
          <DataTable table={m.table("f10.challenges")} />
        </section>
        {csi ? (
          <section aria-label="Characteristic stability">
            <h2 className="font-serif text-2xl mb-2">Characteristic stability, scorecard</h2>
            <DataTable table={csi} />
            <p className="text-xs text-ink2 mt-2">{m.label("f10.pd_csi")}</p>
          </section>
        ) : null}
      </div>
      <Examiner>
        An examiner would ask who validated these models and how independent that was. Here the builder and the validator are
        the same analyst, which SR 11-7 would not accept for a real bank; the reports are written to the standard a separate
        validation team would hold them to, every challenge is logged with its date and its consequence, and a model whose
        report concludes not approved is shadow scored only: the API serves no decision from it.
      </Examiner>
    </>
  );
}
