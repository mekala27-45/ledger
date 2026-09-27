"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Column {
  name: string;
  type: string;
}
interface TableSchema {
  table: string;
  rows: number;
  columns: Column[];
}
type Cell = string | number | boolean | null;
interface Result {
  columns: string[];
  rows: Cell[][];
  total: number;
  ms: number;
}
interface Connection {
  query: (sql: string) => Promise<{
    schema: { fields: { name: string; type: { toString(): string } }[] };
    numRows: number;
    toArray: () => { toJSON: () => Record<string, unknown> }[];
  }>;
}

const SHOWN = 500;

function cell(value: unknown, type: string): Cell {
  if (value === null || value === undefined) return null;
  if (typeof value === "bigint") return Number(value);
  if (type.startsWith("Date") && typeof value === "number") return new Date(value).toISOString().slice(0, 10);
  if (type.startsWith("Timestamp") && typeof value === "number") return new Date(value).toISOString().replace("T", " ").slice(0, 19);
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") return value;
  return String(value);
}

export function ExploreClient({ base, schema, examples }: { base: string; schema: TableSchema[]; examples: { title: string; sql: string }[] }) {
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [problem, setProblem] = useState("");
  const [sql, setSql] = useState(examples[0]?.sql ?? "select * from bank_month limit 20");
  const [result, setResult] = useState<Result | null>(null);
  const [running, setRunning] = useState(false);
  const conn = useRef<Connection | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const duckdb = await import("@duckdb/duckdb-wasm/dist/duckdb-browser.mjs");
        const worker = new Worker(`${base}/duckdb/duckdb-browser-eh.worker.js`);
        const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
        await db.instantiate(`${base}/duckdb/duckdb-eh.wasm`);
        const c = await db.connect();
        // Arrow IPC inserts need no DuckDB extension, so nothing is fetched from anywhere but this site.
        for (const t of schema) {
          const bytes = new Uint8Array(await (await fetch(`${base}/data/explore/${t.table}.arrow`)).arrayBuffer());
          await c.insertArrowFromIPCStream(bytes, { name: t.table });
        }
        if (!cancelled) {
          conn.current = c as unknown as Connection;
          setStatus("ready");
        }
      } catch (err) {
        if (!cancelled) {
          setStatus("failed");
          setProblem(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [base, schema]);

  const run = useCallback(async () => {
    if (!conn.current) return;
    setRunning(true);
    setProblem("");
    const started = performance.now();
    try {
      const table = await conn.current.query(sql);
      const fields = table.schema.fields.map((f) => ({ name: f.name, type: f.type.toString() }));
      const rows = table
        .toArray()
        .slice(0, SHOWN)
        .map((r) => {
          const json = r.toJSON();
          return fields.map((f) => cell(json[f.name], f.type));
        });
      setResult({ columns: fields.map((f) => f.name), rows, total: table.numRows, ms: performance.now() - started });
    } catch (err) {
      setResult(null);
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [sql]);

  useEffect(() => {
    if (status === "ready") void run();
    // Run the first example once the database is ready, not on every edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
      <aside className="xl:col-span-1 border border-hairline bg-raised rounded-md p-3 text-xs max-h-[640px] overflow-y-auto" aria-label="Tables">
        <h2 className="text-sm font-semibold mb-2">Tables</h2>
        <ul className="space-y-3" data-testid="schema">
          {schema.map((t) => (
            <li key={t.table}>
              <button
                type="button"
                className="font-mono underline text-ink"
                onClick={() => setSql(`select * from ${t.table} limit 50`)}
              >
                {t.table}
              </button>{" "}
              <span className="text-ink2 num">{t.rows.toLocaleString("en-US")} rows</span>
              <ul className="mt-1 pl-2 text-ink2 font-mono text-[10.5px] leading-snug">
                {t.columns.map((c) => (
                  <li key={c.name}>
                    {c.name} <span className="opacity-70">{c.type.toLowerCase()}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </aside>
      <div className="xl:col-span-3 space-y-3">
        <div className="flex flex-wrap gap-2 text-xs">
          {examples.map((e) => (
            <button key={e.title} type="button" className="px-2 py-0.5 border border-hairline rounded text-ink2 hover:text-ink" onClick={() => setSql(e.sql)}>
              {e.title}
            </button>
          ))}
        </div>
        <label className="block text-xs text-ink2" htmlFor="sql">
          SQL, DuckDB dialect. Ctrl or Cmd and Enter runs it.
        </label>
        <textarea
          id="sql"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void run();
            }
          }}
          rows={7}
          spellCheck={false}
          className="w-full font-mono text-[12.5px] bg-surface border border-hairline rounded p-3 text-ink"
          data-testid="sql"
        />
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            onClick={() => void run()}
            disabled={status !== "ready" || running}
            className="px-3 py-1.5 rounded bg-accent text-surface font-semibold disabled:opacity-50"
            data-testid="run"
          >
            {running ? "Running…" : "Run"}
          </button>
          <span className="text-xs text-ink2" role="status" data-testid="explore-status">
            {status === "loading" && "Loading DuckDB in your browser…"}
            {status === "failed" && "DuckDB could not start in this browser."}
            {status === "ready" && result && `${result.total.toLocaleString("en-US")} rows in ${result.ms.toFixed(0)} ms${result.total > SHOWN ? `, first ${SHOWN} shown` : ""}.`}
          </span>
        </div>
        {problem ? <p className="text-critical text-sm font-mono whitespace-pre-wrap">{problem}</p> : null}
        {result ? (
          <div className="overflow-auto max-h-[520px] border border-hairline bg-raised rounded-md" tabIndex={0} role="region" aria-label="Query result">
            <table className="data-table w-full" data-testid="result">
              <thead className="sticky top-0 bg-raised">
                <tr>
                  {result.columns.map((c) => (
                    <th key={c} className="font-mono">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((v, j) => (
                      <td key={j} className={typeof v === "number" ? "num font-mono" : "font-mono"}>
                        {v === null ? <span className="text-ink2">null</span> : typeof v === "number" ? String(Number(v.toPrecision(12))) : String(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
}
