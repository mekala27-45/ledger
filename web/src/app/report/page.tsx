import type { Metadata } from "next";
import Link from "next/link";

import { readText } from "@/lib/data";

import { PrintButton } from "./PrintButton";

export const metadata: Metadata = { title: "Board pack" };

export default function Report() {
  // Rendered from report/board-pack.md by the pipeline with raw HTML disabled; every number
  // in it came from the manifest through the claim gate.
  const html = readText("reports/board-pack.html");
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 no-print">
        <p className="text-xs uppercase tracking-[0.14em] text-ink2">Function 12 · the board pack</p>
        <div className="flex items-center gap-3">
          <Link href="/definitions/" className="text-xs underline text-ink2">
            Definitions
          </Link>
          <PrintButton />
        </div>
      </div>
      <article data-theme="light" className="report-sheet bg-surface text-ink rounded-md px-5 py-8 sm:px-12 sm:py-12 max-w-4xl" data-testid="board-pack">
        <div className="prose-ledger report" dangerouslySetInnerHTML={{ __html: html }} />
      </article>
    </>
  );
}
