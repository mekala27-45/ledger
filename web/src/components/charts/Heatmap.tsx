"use client";

import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { SEQUENTIAL, useWidth } from "./useWidth";

/**
 * A matrix on the sequential ramp, rows and columns in their natural order. The step is
 * chosen on a log scale because transition rates run from a fraction of a percent to
 * nearly one; each cell also prints its value, so colour is never the only channel.
 */
export function Heatmap({
  rows,
  columns,
  cells,
  fmt,
  rowLabel,
  columnLabel,
}: {
  rows: string[];
  columns: string[];
  /** cells[i][j] is the value for rows[i] and columns[j]; null is an empty cell. */
  cells: (number | null)[][];
  fmt: string;
  rowLabel: string;
  columnLabel: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const left = 88;
  const top = 34;
  const cellW = Math.max((width - left - 8) / columns.length, 36);
  const cellH = 40;
  const step = (v: number) => {
    const t = Math.log10(Math.max(v, 1e-4)) / 4 + 1; // 1e-4 maps to 0, 1 maps to 1
    return SEQUENTIAL[Math.min(SEQUENTIAL.length - 1, Math.max(0, Math.floor(t * SEQUENTIAL.length)))] ?? SEQUENTIAL[0];
  };
  return (
    <div ref={ref} className="relative w-full overflow-x-auto" onMouseLeave={() => setTip(null)}>
      <svg width={left + cellW * columns.length + 8} height={top + cellH * rows.length + 8} role="img" aria-label={`${rowLabel} by ${columnLabel}`}>
        <text x={left} y={12} className="fill-[var(--ink2)] text-[11px]">
          {columnLabel}
        </text>
        {columns.map((c, j) => (
          <text key={c} x={left + j * cellW + cellW / 2} y={28} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
            {c}
          </text>
        ))}
        {rows.map((r, i) => (
          <g key={r}>
            <text x={left - 8} y={top + i * cellH + cellH / 2} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[11px]">
              {r}
            </text>
            {columns.map((c, j) => {
              const v = cells[i]?.[j] ?? null;
              const fill = v === null ? "var(--surface)" : step(v);
              const dark = v !== null && Math.log10(Math.max(v, 1e-4)) / 4 + 1 > 0.55;
              return (
                <g
                  key={c}
                  onMouseEnter={() =>
                    setTip({ x: left + j * cellW + cellW / 2, y: top + i * cellH, lines: [`${r} to ${c}`, formatValue(v, fmt)] })
                  }
                >
                  <rect x={left + j * cellW + 1} y={top + i * cellH + 1} width={cellW - 2} height={cellH - 2} fill={fill} rx={2} />
                  <text
                    x={left + j * cellW + cellW / 2}
                    y={top + i * cellH + cellH / 2}
                    dy="0.32em"
                    textAnchor="middle"
                    className="text-[11px] num"
                    fill={dark ? "var(--surface)" : "var(--ink)"}
                  >
                    {v === null ? "" : formatValue(v, fmt)}
                  </text>
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <p className="text-xs text-ink2">
        Rows: {rowLabel}. The further a cell sits from the background, the larger its share, on a log scale.
      </p>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
