"use client";

import { type ReactNode, useId, useState } from "react";

import { formatValue, type Scalar } from "@/lib/format";

export interface TableData {
  columns: string[];
  formats: string[];
  /** A missing cell (undefined) prints as a null would. */
  rows: (Scalar | undefined)[][];
}

/** Every chart: a title, the chart or its table, one written callout, and its provenance label. */
export function ChartFrame({
  title,
  callout,
  label,
  table,
  children,
  wide = false,
}: {
  title: string;
  callout: string;
  label: string;
  table: TableData;
  children: ReactNode;
  wide?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  return (
    <figure className={`border border-hairline bg-raised rounded-md p-4 ${wide ? "xl:col-span-2" : ""}`} aria-labelledby={id}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 id={id} className="text-sm font-semibold text-ink leading-snug">
          {title}
        </h3>
        <button
          type="button"
          onClick={() => setShowTable((s) => !s)}
          className="no-print text-xs px-2 py-0.5 border border-hairline rounded text-ink2 hover:text-ink shrink-0"
          aria-pressed={showTable}
          data-testid="table-toggle"
        >
          {showTable ? "Chart" : "Table"}
        </button>
      </div>
      {showTable ? <DataTable table={table} /> : children}
      <figcaption className="mt-3 text-sm text-ink leading-relaxed">{callout}</figcaption>
      <p className="mt-2 text-xs text-ink2">{label}</p>
    </figure>
  );
}

export function DataTable({ table, max = 400 }: { table: TableData; max?: number }) {
  const rows = table.rows.slice(0, max);
  return (
    <div className="overflow-x-auto max-h-[420px] overflow-y-auto" role="region" aria-label="Chart data" tabIndex={0}>
      <table className="data-table">
        <thead>
          <tr>
            {table.columns.map((c, i) => (
              <th key={c} className={table.formats[i] === "text" ? "" : "num"}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) => (
                <td key={i} className={table.formats[i] === "text" ? "" : "num"}>
                  {formatValue(cell, table.formats[i] ?? "text")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.rows.length > max ? <p className="text-xs text-ink2 mt-2">First {max} of {table.rows.length} rows.</p> : null}
    </div>
  );
}

export function ManifestTable({ table }: { table: TableData }) {
  return <DataTable table={table} />;
}
