import Link from "next/link";
import type { ReactNode } from "react";

import { manifest, statements } from "@/lib/data";

import { ThemeToggle } from "./ThemeToggle";

export const REPO = "https://github.com/mekala27-45/ledger";

// A function's page is listed once its function has written results to the manifest, so
// the navigation never links to a page that does not exist yet.
const NAV: [string, string, string | null][] = [
  ["/", "Glance", null],
  ["/desk/", "Desk", "f04."],
  ["/studio/", "Studio", "models.pd_scorecard."],
  ["/lending/", "Lending", "f02."],
  ["/fair-lending/", "Fair lending", "f03."],
  ["/crime/", "Crime", "f05."],
  ["/deposits/", "Deposits", "f06."],
  ["/complaints/", "Complaints", "f07."],
  ["/treasury/", "Treasury", "f08."],
  ["/collections/", "Collections", "f09."],
  ["/models/", "Models", "f10."],
  ["/controls/", "Controls", "f11."],
  ["/explore/", "Explore", null],
  ["/report/", "Board pack", "f12."],
];

export function Shell({ children }: { children: ReactNode }) {
  const s = statements();
  const m = manifest();
  const nav = NAV.filter(([, , needs]) => needs === null || m.hasPrefix(needs));
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-hairline bg-surface/95 backdrop-blur sticky top-0 z-30">
        <div className="mx-auto max-w-[1400px] px-4 sm:px-6 flex items-center gap-4 h-14">
          <Link href="/" className="flex items-baseline gap-2 shrink-0" aria-label="ledger home">
            <span className="font-serif text-2xl leading-none">ledger</span>
            <span className="hidden sm:inline text-xs text-ink2">Harborline Bank, fictional</span>
          </Link>
          <nav aria-label="Functions" className="flex-1 overflow-x-auto">
            <ul className="flex gap-1 text-sm whitespace-nowrap">
              {nav.map(([href, label]) => (
                <li key={href}>
                  <Link href={href} className="px-2 py-1 rounded text-ink2 hover:text-ink hover:bg-raised">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-[1400px] px-4 sm:px-6 py-6">{children}</main>
      <footer className="border-t border-hairline mt-10" data-testid="statements">
        <div className="mx-auto max-w-[1400px] px-4 sm:px-6 py-6 text-xs text-ink2 space-y-1">
          <p data-statement="demonstration">{s.demonstration}</p>
          <p data-statement="not-a-decision">{s.not_a_decision}</p>
          <p>
            Built by Ajay Mekala.{" "}
            <a className="underline" href={REPO}>
              Source on GitHub
            </a>
            , Apache 2.0. Every dataset&apos;s source and licence is in{" "}
            <a className="underline" href={`${REPO}/blob/main/data/PROVENANCE.md`}>
              data/PROVENANCE.md
            </a>
            .
          </p>
        </div>
      </footer>
    </div>
  );
}
