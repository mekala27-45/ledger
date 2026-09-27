"use client";

import { scaleLog } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { useWidth } from "./useWidth";

export interface ForestRow {
  section: string;
  label: string;
  a: { value: number; low: number; high: number };
  b: { value: number; low: number; high: number };
}

/**
 * Two estimates per row on one log axis with a line at one: a circle for the first
 * (unadjusted) and a diamond for the second (adjusted), each with its interval. Shape,
 * not only colour, tells them apart.
 */
export function Forest({ rows, aLabel, bLabel, xLabel }: { rows: ForestRow[]; aLabel: string; bLabel: string; xLabel: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const left = Math.min(190, Math.max(120, width * 0.3));
  const right = 16;
  const rowH = 34;
  const sections = [...new Set(rows.map((r) => r.section))];
  const lines: ({ kind: "section"; text: string } | { kind: "row"; row: ForestRow })[] = [];
  for (const s of sections) {
    lines.push({ kind: "section", text: s });
    for (const r of rows.filter((x) => x.section === s)) lines.push({ kind: "row", row: r });
  }
  const values = rows.flatMap((r) => [r.a.low, r.a.high, r.b.low, r.b.high]).filter((v) => v > 0);
  const lo = Math.min(0.5, ...values) * 0.95;
  const hi = Math.max(2, ...values) * 1.05;
  const x = scaleLog().domain([lo, hi]).range([left, width - right]);
  const ticks = [0.5, 0.75, 1, 1.5, 2, 3].filter((t) => t >= lo && t <= hi);
  const height = lines.length * rowH + 44;
  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg width={width} height={height} role="img" aria-label={xLabel}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={8} y2={height - 30} stroke={t === 1 ? "var(--ink2)" : "var(--hairline)"} strokeDasharray={t === 1 ? "" : "2 3"} />
            <text x={x(t)} y={height - 16} textAnchor="middle" className="fill-[var(--ink2)] text-[11px] num">
              {t}
            </text>
          </g>
        ))}
        <text x={(left + width - right) / 2} y={height - 2} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
          {xLabel}
        </text>
        {lines.map((line, i) => {
          const y = 14 + i * rowH;
          if (line.kind === "section") {
            return (
              <text key={`s-${line.text}`} x={0} y={y + 10} className="fill-[var(--ink)] text-[12px] font-semibold">
                {line.text}
              </text>
            );
          }
          const r = line.row;
          const ya = y + 8;
          const yb = y + 20;
          const tipFor = () =>
            setTip({
              x: x(r.b.value),
              y,
              lines: [
                r.label,
                `${aLabel}: ${formatValue(r.a.value, "float2")} (${formatValue(r.a.low, "float2")} to ${formatValue(r.a.high, "float2")})`,
                `${bLabel}: ${formatValue(r.b.value, "float2")} (${formatValue(r.b.low, "float2")} to ${formatValue(r.b.high, "float2")})`,
              ],
            });
          return (
            <g key={`r-${r.section}-${r.label}`} onMouseEnter={tipFor} onFocus={tipFor} tabIndex={0}>
              <rect x={0} y={y} width={width} height={rowH - 4} fill="transparent" />
              <text x={12} y={y + 17} className="fill-[var(--ink)] text-[12px]">
                {r.label}
              </text>
              <line x1={x(r.a.low)} x2={x(r.a.high)} y1={ya} y2={ya} stroke="var(--cat-2)" strokeWidth={2} />
              <circle cx={x(r.a.value)} cy={ya} r={4.5} fill="var(--cat-2)" />
              <line x1={x(r.b.low)} x2={x(r.b.high)} y1={yb} y2={yb} stroke="var(--cat-1)" strokeWidth={2} />
              <path d={`M${x(r.b.value)},${yb - 6}l6,6l-6,6l-6,-6z`} fill="var(--cat-1)" />
            </g>
          );
        })}
      </svg>
      <ul className="flex flex-wrap gap-4 text-xs text-ink2" aria-label="Legend">
        <li className="flex items-center gap-1">
          <svg width="12" height="12" aria-hidden="true">
            <circle cx="6" cy="6" r="4.5" fill="var(--cat-2)" />
          </svg>
          {aLabel}
        </li>
        <li className="flex items-center gap-1">
          <svg width="12" height="12" aria-hidden="true">
            <path d="M6,0l6,6l-6,6l-6,-6z" fill="var(--cat-1)" />
          </svg>
          {bLabel}
        </li>
      </ul>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
