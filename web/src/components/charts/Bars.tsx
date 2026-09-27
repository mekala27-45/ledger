"use client";

import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { ORDINAL, useWidth } from "./useWidth";

/** Horizontal bars, one per ordered category, value printed at the end of each bar. */
export function Bars({
  items,
  fmt,
  ordinal = true,
}: {
  items: { label: string; value: number; note?: string }[];
  fmt: string;
  ordinal?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const left = 180;
  const rowH = 30;
  const innerW = Math.max(width - left - 90, 120);
  const max = Math.max(...items.map((d) => Math.abs(d.value)), 1e-9);
  const x = scaleLinear().domain([0, max]).range([0, innerW]);
  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg width={width} height={items.length * rowH + 8} role="img" aria-label="Bar chart">
        <defs>
          <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line y2="6" stroke="var(--surface)" strokeWidth="1.5" opacity="0.35" />
          </pattern>
        </defs>
        {items.map((d, i) => {
          const color = ordinal ? ORDINAL[Math.min(i, ORDINAL.length - 1)] : "var(--cat-1)";
          return (
            <g
              key={d.label}
              transform={`translate(0,${i * rowH + 4})`}
              onMouseEnter={() => setTip({ x: left + x(Math.abs(d.value)), y: i * rowH, lines: [d.label, formatValue(d.value, fmt), d.note ?? ""] })}
            >
              <text x={left - 10} y={rowH / 2 - 2} dy="0.32em" textAnchor="end" className="fill-[var(--ink)] text-[12px]">
                {d.label}
              </text>
              <rect x={left} y={3} width={x(Math.abs(d.value))} height={rowH - 10} fill={color} rx={2} />
              <rect x={left} y={3} width={x(Math.abs(d.value))} height={rowH - 10} fill="url(#hatch)" rx={2} />
              <text x={left + x(Math.abs(d.value)) + 6} y={rowH / 2 - 2} dy="0.32em" className="fill-[var(--ink)] text-[11px] num">
                {formatValue(d.value, fmt)}
              </text>
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
