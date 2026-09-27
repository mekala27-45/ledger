import type { Metadata } from "next";

import { readText } from "@/lib/data";

export const metadata: Metadata = { title: "Definitions" };

export default function Definitions() {
  const html = readText("reports/definitions.html");
  return (
    <article className="max-w-4xl">
      <div className="prose-ledger report" dangerouslySetInnerHTML={{ __html: html }} />
    </article>
  );
}
