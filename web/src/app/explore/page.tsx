import type { Metadata } from "next";

import { Examiner, PageHeader } from "@/components/Section";
import { readJson } from "@/lib/data";

import { ExploreClient } from "./ExploreClient";

export const metadata: Metadata = { title: "Explore the warehouse" };

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

interface TableSchema {
  table: string;
  rows: number;
  columns: { name: string; type: string }[];
}

const EXAMPLES = [
  {
    title: "The bank by month",
    sql: "select month, total_assets, total_loans, total_deposits, net_income\nfrom bank_month\norder by month desc\nlimit 12",
  },
  {
    title: "Vintages at twelve months",
    sql: "select vintage, cumulative_default_rate\nfrom vintage_curves\nwhere months_on_book = 12\norder by vintage",
  },
  {
    title: "The break, found by hand",
    sql: "select gl_account, month, balance_from_postings, reported_balance,\n       reported_balance - balance_from_postings as difference\nfrom gl_account_month\nwhere reported_balance <> balance_from_postings\norder by month",
  },
  {
    title: "Peers by net interest margin",
    sql: "select name, state, total_assets_thousands, nim_pct\nfrom fdic_peers\nwhere report_date = (select max(report_date) from fdic_peers)\norder by nim_pct desc\nlimit 25",
  },
  {
    title: "Severely adverse unemployment",
    sql: "select scenario, quarter, unemployment_rate\nfrom scenarios\nwhere scenario = 'severely_adverse'\norder by quarter",
  },
];

export default function Explore() {
  const schema = readJson<TableSchema[]>("explore/schema.json");
  return (
    <>
      <PageHeader
        kicker="Explore"
        question="Want to check a number yourself?"
        answer={
          <p>
            The warehouse&apos;s published marts load into DuckDB running in your browser. Nothing is sent anywhere: the
            queries run on this machine against the same aggregates the pages are drawn from. No customer level table is
            published.
          </p>
        }
      />
      <ExploreClient base={BASE} schema={schema} examples={EXAMPLES} />
      <Examiner>
        An examiner would ask whether the numbers on the other pages can be reproduced from the data rather than taken on
        trust. The example that finds the ledger break by hand is the control&apos;s query in five lines; the peer query is
        the FDIC&apos;s own financial data for the latest quarter, before any ratio is computed.
      </Examiner>
    </>
  );
}
