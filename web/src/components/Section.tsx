import type { ReactNode } from "react";

/** A function page opens with its question in the display serif and the answer under it. */
export function PageHeader({ kicker, question, answer }: { kicker: string; question: string; answer: ReactNode }) {
  return (
    <div className="mb-8 max-w-4xl">
      <p className="text-xs uppercase tracking-[0.14em] text-ink2 mb-2">{kicker}</p>
      <h1 className="font-serif text-4xl sm:text-5xl leading-[1.05] mb-4">{question}</h1>
      <div className="text-base text-ink leading-relaxed prose-ledger">{answer}</div>
    </div>
  );
}

export function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">{children}</div>;
}

export function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="border border-hairline bg-raised rounded-md px-4 py-3">
      <div className="text-xs text-ink2">{label}</div>
      <div className="text-2xl num text-left mt-1">{value}</div>
      {note ? <div className="text-xs text-ink2 mt-1">{note}</div> : null}
    </div>
  );
}

export function Examiner({ children }: { children: ReactNode }) {
  return (
    <aside className="mt-10 border-l-2 border-accent pl-4 max-w-3xl" aria-label="What the examiner would ask">
      <h2 className="font-serif text-2xl mb-2">What the examiner would ask</h2>
      <div className="text-sm text-ink leading-relaxed">{children}</div>
    </aside>
  );
}

export function Limitations({ items }: { items: string[] }) {
  return (
    <section className="mt-8 max-w-3xl">
      <h2 className="font-serif text-2xl mb-2">Method and limitations</h2>
      <ul className="list-disc pl-5 text-sm space-y-1 text-ink">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
