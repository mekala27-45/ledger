"use client";

import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { useWidth } from "./useWidth";

/** Horizontal bars either side of zero, one per row: a tornado when the rows are shocks. */
export function Diverging({
  items,
  fmt,
  zeroLabel = "0",
}: {
  items: { label: string; value: number; note?: string }[];
  fmt: string;
  zeroLabel?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const left = 120;
  const pad = 96;
  const rowH = 32;
  const max = Math.max(...items.map((d) => Math.abs(d.value)), 1e-9);
  const x = scaleLinear()
    .domain([-max, max])
    .range([left + pad, Math.max(width - pad, left + pad + 80)]);
  const zero = x(0);
  const height = items.length * rowH + 28;
  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg width={width} height={height} role="img" aria-label="Diverging bar chart">
        <line x1={zero} x2={zero} y1={0} y2={height - 20} stroke="var(--hairline)" />
        <text x={zero} y={height - 6} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
          {zeroLabel}
        </text>
        {items.map((d, i) => {
          const end = x(d.value);
          const negative = d.value < 0;
          const y = i * rowH + 4;
          return (
            <g
              key={d.label}
              onMouseEnter={() => setTip({ x: end, y, lines: [d.label, formatValue(d.value, fmt), d.note ?? ""] })}
            >
              <text x={left - 10} y={y + rowH / 2 - 2} dy="0.32em" textAnchor="end" className="fill-[var(--ink)] text-[12px]">
                {d.label}
              </text>
              <rect
                x={Math.min(zero, end)}
                y={y + 3}
                width={Math.max(Math.abs(end - zero), 1)}
                height={rowH - 12}
                fill={negative ? "var(--cat-2)" : "var(--cat-1)"}
                rx={2}
              />
              <text
                x={negative ? Math.min(zero, end) - 6 : Math.max(zero, end) + 6}
                y={y + rowH / 2 - 2}
                dy="0.32em"
                textAnchor={negative ? "end" : "start"}
                className="fill-[var(--ink)] text-[11px] num"
              >
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
