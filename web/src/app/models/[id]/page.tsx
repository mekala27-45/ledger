import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { readJson, readText } from "@/lib/data";

import type { RegistryEntry } from "../page";

export function generateStaticParams(): { id: string }[] {
  const registry = readJson<Record<string, RegistryEntry>>("models/registry.json");
  return Object.keys(registry).map((id) => ({ id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `Validation report: ${id}` };
}

export default async function Report({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const registry = readJson<Record<string, RegistryEntry>>("models/registry.json");
  const entry = registry[id];
  if (!entry) notFound();
  // Rendered from report/validation/<id>.md by the pipeline with raw HTML disabled.
  const html = readText(`reports/${id}.html`);
  return (
    <article className="max-w-4xl">
      <p className="text-xs uppercase tracking-[0.14em] text-ink2 mb-2">
        <Link href="/models/" className="underline">
          Model risk
        </Link>{" "}
        · validation report · <span className="font-mono normal-case tracking-normal">{id}</span>
      </p>
      <div className="prose-ledger report" dangerouslySetInnerHTML={{ __html: html }} />
    </article>
  );
}
