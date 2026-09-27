import type { Metadata } from "next";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { Examiner, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson } from "@/lib/data";
import { formatValue } from "@/lib/format";

export const metadata: Metadata = { title: "Controls and data" };

type Row = Record<string, number | string | null>;

export default function Controls() {
  const m = manifest();
  const recon = readJson<Row[]>("f11/reconciliation.json");
  const accounts = [...new Set(recon.map((r) => String(r.gl_account)))].sort();
  const months = [...new Set(recon.map((r) => String(r.month)))].sort();
  const status = new Map(recon.map((r) => [`${r.gl_account}|${r.month}`, r]));
  const breakAccount = String(m.raw("f11.break_account"));
  const breakRows = recon.filter((r) => String(r.gl_account) === breakAccount).sort((a, b) => String(a.month).localeCompare(String(b.month)));
  const dq = m.table("f11.dq_table");

  const cell = 14;
  const left = 46;
  const top = 8;
  const gridW = left + months.length * cell + 4;
  const gridH = top + accounts.length * cell + 30;
  return (
    <>
      <PageHeader
        kicker="Function 11 · controls and data"
        question="Can every other number here be trusted?"
        answer={
          <p>
            The general ledger rebuilt from its postings ties to the reported balances in {m.v("f11.account_months_tied")} of{" "}
            {m.v("f11.account_months")} account months, to the cent. The rest are one break, planted to prove the control
            works: account {m.v("f11.break_account")}, {m.v("f11.break_amount")}, first in {m.v("f11.break_month")} and
            carried into {m.v("f11.break_months_carried")} month ends because nothing later corrects it. Every sub ledger
            check ties ({m.v("f11.subledger_tied")} of {m.v("f11.subledger_checks")}), every data quality defect that was
            injected was caught at its injected count, and the warehouse passes {m.v("f11.dbt_tests_passed")} of{" "}
            {m.v("f11.dbt_tests")} tests.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Account months tied to the cent" value={`${m.v("f11.account_months_tied")} of ${m.v("f11.account_months")}`} />
        <Kpi label="Postings with no source transaction" value={m.v("f11.unsourced_postings")} />
        <Kpi label="Injected defects caught" value={`${m.v("f11.injected_caught")} of ${m.v("f11.injected_defects")}`} note={`${m.v("f11.dq_rules")} rules run`} />
        <Kpi label="Planted identifiers found in staged data" value={m.v("f11.identifier_findings")} note={`${m.v("f11.tables_scanned")} tables scanned`} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <figure className="border border-hairline bg-raised rounded-md p-4">
          <h3 className="text-sm font-semibold mb-3">{m.figure("f11.fig_recon").title}</h3>
          <div className="overflow-x-auto">
            <svg width={gridW} height={gridH} role="img" aria-label="Reconciliation status by account and month" data-testid="recon-grid">
              {accounts.map((a, i) => (
                <text key={a} x={left - 6} y={top + i * cell + cell / 2} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[9px] font-mono">
                  {a}
                </text>
              ))}
              {accounts.map((a, i) =>
                months.map((mo, j) => {
                  const r = status.get(`${a}|${mo}`);
                  if (!r) return null;
                  const tied = r.status === "tied";
                  const x = left + j * cell;
                  const y = top + i * cell;
                  return (
                    <g key={`${a}-${mo}`}>
                      <rect x={x + 1} y={y + 1} width={cell - 2} height={cell - 2} rx={2} fill={tied ? "var(--good)" : "var(--critical)"} opacity={tied ? 0.35 : 1}>
                        <title>{`${a} ${mo}: ${tied ? "tied" : `off by ${formatValue(Number(r.difference), "usd2")}`}`}</title>
                      </rect>
                      {tied ? null : (
                        <path d={`M${x + 3.5},${y + 3.5}l${cell - 7},${cell - 7}M${x + cell - 3.5},${y + 3.5}l-${cell - 7},${cell - 7}`} stroke="var(--surface)" strokeWidth={1.6} />
                      )}
                    </g>
                  );
                }),
              )}
              {months.map((mo, j) =>
                j % 6 === 0 ? (
                  <text key={mo} x={left + j * cell} y={top + accounts.length * cell + 14} className="fill-[var(--ink2)] text-[9px] font-mono">
                    {mo}
                  </text>
                ) : null,
              )}
            </svg>
          </div>
          <p className="text-xs text-ink2 mt-1">Each square is one account at one month end: pale is tied, a solid square with a cross is a break.</p>
          <figcaption className="mt-3 text-sm leading-relaxed">{m.figure("f11.fig_recon").callout}</figcaption>
          <p className="mt-2 text-xs text-ink2">{m.label("f11.fig_recon")}</p>
        </figure>
        <ChartFrame
          title={`Account ${breakAccount}: reported balance less the sum of its postings`}
          callout={`The difference is zero until ${m.v("f11.break_month")}, then holds at ${formatValue(Number(breakRows.find((r) => r.status !== "tied")?.difference ?? 0), "usd2")} in every later month, which is what one unposted or misposted entry looks like: a step, not a drift.`}
          label={m.label("f11.breaks_table")}
          table={{
            columns: ["Month", "From postings", "Reported", "Difference", "Status"],
            formats: ["text", "usd2", "usd2", "usd2", "text"],
            rows: breakRows.map((r) => [r.month, r.balance_from_postings, r.reported_balance, r.difference, r.status]),
          }}
        >
          <LineChart
            series={[{ name: "Difference", points: breakRows.map((r) => ({ x: String(r.month), y: Number(r.difference) })), emphasis: true }]}
            markers={[{ x: String(m.raw("f11.break_month")), label: "break", color: "var(--critical)" }]}
            yFormat="usd0"
            xLabel="Month end"
            yLabel="Reported less postings"
            points
          />
        </ChartFrame>
      </div>

      <section className="mt-10" aria-label="Data quality">
        <h2 className="font-serif text-2xl mb-2">Every data quality rule, with its hits</h2>
        <p className="text-sm mb-3 max-w-3xl">
          Three defects were injected into the generated data at known counts; each rule that should find one must find exactly
          that many. The real datasets&apos; own issues are counted by the same rules and left in view rather than cleaned
          away.
        </p>
        <div className="overflow-x-auto border border-hairline bg-raised rounded-md p-3">
          <table className="data-table w-full" data-testid="dq-table">
            <thead>
              <tr>
                {dq.columns.map((c, i) => (
                  <th key={c} className={dq.formats[i] === "text" ? "" : "num"}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dq.rows.map((r) => (
                <tr key={`${String(r[0])}-${String(r[1])}`}>
                  {r.map((v, i) => (
                    <td key={i} className={dq.formats[i] === "text" ? (i === 6 && v ? "text-good" : "") : "num"}>
                      {i === 6 && v ? `✓ ${String(v)}` : v === null ? "" : formatValue(v, dq.formats[i] ?? "text")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-ink2 mt-2">{m.label("f11.dq_table")}</p>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-10">
        <Kpi label="FDIC institutions checked for the bank's name" value={m.v("f11.fdic_institutions")} note={`${m.v("f11.bank_name_collisions")} collisions, active or inactive`} />
        <Kpi label="Warehouse models built" value={m.v("f11.dbt_models")} note={`${m.v("f11.dbt_tests_passed")} of ${m.v("f11.dbt_tests")} tests pass`} />
        <Kpi label="FDIC peers that stop reporting in the window" value={m.v("f11.fdic_stopped_reporting")} note="Found by rule and left out of the latest quarter's peer group" />
      </div>
      <section className="mt-6">
        <h2 className="font-serif text-2xl mb-2">The break, as the control reports it</h2>
        <DataTable table={m.table("f11.breaks_table")} />
      </section>
      <Limitations
        items={[
          "The ledger and its sub ledgers are generated, so the control is proved on a known answer: the planted break's account, month and amount are in the truth tables, and the test fails if the control reports anything else.",
          "Reconciliation compares balances at month end. An offsetting pair of errors inside one month would tie; the sub ledger checks and the unsourced posting count are there for that.",
        ]}
      />
      <Examiner>
        An examiner would ask whether a break this size would be noticed without being planted. It would: the comparison is
        exact decimal arithmetic in whole cents, not a tolerance, so a single cent in any account month fails the tie, and the
        data quality rules report their hit counts on every run whether or not anything was injected.
      </Examiner>
    </>
  );
}
