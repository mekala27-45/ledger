import type { Metadata } from "next";
import Link from "next/link";

import { DataTable } from "@/components/charts/ChartFrame";
import { Examiner, Kpi, Limitations, PageHeader } from "@/components/Section";
import { manifest, readJson, statements } from "@/lib/data";
import { formatValue } from "@/lib/format";

import type { Card, FineBin } from "./scorecard";
import { StudioClient } from "./StudioClient";

export const metadata: Metadata = { title: "Scorecard studio" };

const API = process.env.NEXT_PUBLIC_LEDGER_API ?? "";

export default function Studio() {
  const m = manifest();
  const card = readJson<Card>("studio/scorecard_generated.json");
  const fine = readJson<Record<string, FineBin[]>>("studio/fine_bins_generated.json");
  const reasons = readJson<Record<string, Record<string, string>>>("studio/reason_codes.json");
  const table = m.table("models.pd_scorecard.scorecard");
  const known = m.table("models.pd_scorecard.known_parameters");
  const ivTable = m.table("models.pd_scorecard.iv");
  const sideBySide = m.table("models.pd_scorecard.side_by_side");
  const reasonMix = m.table("models.pd_scorecard.reasons");
  const groups = new Map<string, (typeof table.rows)[number][]>();
  for (const row of table.rows) {
    const key = String(row[0]);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return (
    <>
      <PageHeader
        kicker="The scorecard studio"
        question="How does a weight of evidence scorecard turn an application into a score and a reason?"
        answer={
          <p>
            Harborline&apos;s installment scorecard keeps {m.v("models.pd_scorecard.characteristics")} of{" "}
            {m.v("models.pd_scorecard.candidates")} candidate characteristics and ranks out of time loans with an AUROC of{" "}
            {m.v("models.pd_scorecard.test.auroc")}. Every point on it comes from a bin&apos;s weight of evidence, so a declined
            applicant&apos;s reasons are the characteristics furthest below their best points. Move a bin edge below and watch
            the information value and the monotonicity respond; then score an applicant at the cutoff of{" "}
            {m.v("models.pd_scorecard.cutoff")}.
          </p>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="AUROC, test months" value={m.v("models.pd_scorecard.test.auroc")} note={`Gini ${m.v("models.pd_scorecard.test.gini")}`} />
        <Kpi label="Characteristics kept" value={`${m.v("models.pd_scorecard.characteristics")} of ${m.v("models.pd_scorecard.candidates")}`} />
        <Kpi label="Cutoff" value={m.v("models.pd_scorecard.cutoff")} note={`Approval rate, test months ${m.v("models.pd_scorecard.approval_rate_test")}`} />
        <Kpi label="Same engine on real accounts" value={m.v("models.pd_scorecard.uci_auroc")} note={`AUROC on ${m.v("models.pd_scorecard.uci_accounts")} UCI credit card accounts`} />
      </div>

      <StudioClient
        card={card}
        fine={fine}
        reasonText={reasons.generated ?? {}}
        minShare={m.num("policy.min_bin_share")}
        ivFloor={m.num("policy.iv_floor")}
        apiUrl={API}
        notADecision={statements().not_a_decision}
      />

      <section className="mt-10" aria-label="The scorecard">
        <h2 className="font-serif text-2xl mb-1">The scorecard</h2>
        <p className="text-sm text-ink2 mb-3 max-w-3xl">
          Points per bin, scaled so {m.v("policy.base_score")} points are odds of {m.v("policy.base_odds")} to one and every{" "}
          {m.v("policy.pdo")} points double the odds. {m.label("models.pd_scorecard.scorecard")}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3" data-testid="scorecard-table">
          {[...groups.entries()].map(([name, rows]) => (
            <div key={name} className="border border-hairline bg-raised rounded-md p-3">
              <h3 className="font-mono text-xs mb-2">{name}</h3>
              <table className="data-table w-full">
                <thead>
                  <tr>
                    <th>Bin</th>
                    <th className="num">Default</th>
                    <th className="num">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={String(r[1])}>
                      <td className="font-mono whitespace-nowrap text-[11px]">{String(r[1])}</td>
                      <td className="num">{formatValue(r[3] ?? null, "pct1")}</td>
                      <td className="num">{formatValue(r[5] ?? null, "float1")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-10">
        <section aria-label="Information value">
          <h2 className="font-serif text-2xl mb-2">Every candidate, kept or dropped</h2>
          <DataTable table={ivTable} />
          <p className="text-xs text-ink2 mt-2">{m.label("models.pd_scorecard.iv")}</p>
        </section>
        <section aria-label="Known parameters">
          <h2 className="font-serif text-2xl mb-2">Did it recover what the generator put in?</h2>
          <p className="text-sm mb-2">
            The loan book was generated with a stated risk structure, so the pipeline had to recover it before any number
            here was trusted.
          </p>
          <DataTable table={known} />
          <p className="text-xs text-ink2 mt-2">{m.label("models.pd_scorecard.known_parameters")}</p>
        </section>
        <section aria-label="Generated and real">
          <h2 className="font-serif text-2xl mb-2">The same engine on real accounts</h2>
          <DataTable table={sideBySide} />
          <p className="text-xs text-ink2 mt-2">{m.label("models.pd_scorecard.side_by_side")}</p>
        </section>
        <section aria-label="Reasons given">
          <h2 className="font-serif text-2xl mb-2">The first reason on declined test applications</h2>
          <DataTable table={reasonMix} />
          <p className="text-xs text-ink2 mt-2">{m.label("models.pd_scorecard.reasons")}</p>
        </section>
      </div>

      <Limitations
        items={[
          "The applications are generated. Nothing here is a real person's credit file, and the bureau score is a generated stand in for one.",
          `The scorecard under predicts default on the loosened vintages (mean predicted ${m.v("models.pd_scorecard.mean_pd_validation")} against ${m.v("models.pd_scorecard.observed_validation")} observed on the validation months), which is why its validation report concludes approved with conditions and expected loss applies an overlay.`,
          "Moving a bin edge in the studio recomputes weight of evidence, information value and points at the fitted coefficient. It does not refit the regression; the pipeline does that.",
        ]}
      />
      <Examiner>
        An examiner would ask whether the adverse action reasons are specific and whether any characteristic stands in for
        a protected class. The reasons are the characteristics furthest below their best attainable points, in plain words
        from a reviewed file, at most four, and the engine refuses to fit or explain with anything on the proxy list. The{" "}
        <Link className="underline" href="/models/pd_scorecard/">validation report</Link> has the rest.
      </Examiner>
    </>
  );
}
