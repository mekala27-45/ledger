"use client";

import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { useWidth } from "./useWidth";

export interface Strip {
  label: string;
  fmt: string;
  peers: number[];
  ours: number;
}

/** One row per ratio: every real peer as a dot, the fictional bank as a labelled diamond. */
export function StripPlot({ strips, oursLabel }: { strips: Strip[]; oursLabel: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const left = 170;
  const rowH = 38;
  const innerW = Math.max(width - left - 24, 160);
  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg width={width} height={strips.length * rowH + 16} role="img" aria-label="Ratios against real peers">
        {strips.map((s, i) => {
          const values = [...s.peers, s.ours].sort((a, b) => a - b);
          const lo = values[Math.floor(values.length * 0.02)] ?? 0;
          const hi = values[Math.ceil(values.length * 0.98) - 1] ?? 1;
          const x = scaleLinear().domain([Math.min(lo, s.ours), Math.max(hi, s.ours)]).range([0, innerW]).clamp(true);
          const yMid = i * rowH + rowH / 2 + 4;
          return (
            <g key={s.label}>
              <text x={left - 10} y={yMid} dy="0.32em" textAnchor="end" className="fill-[var(--ink)] text-[12px]">
                {s.label}
              </text>
              <line x1={left} x2={left + innerW} y1={yMid} y2={yMid} stroke="var(--hairline)" />
              {s.peers.map((v, j) => (
                <circle
                  key={j}
                  cx={left + x(v)}
                  cy={yMid + (((j * 7919) % 11) - 5) * 1.4}
                  r={2.4}
                  fill="var(--cat-2)"
                  opacity={0.55}
                  onMouseEnter={() => setTip({ x: left + x(v), y: yMid - 10, lines: ["Real peer", formatValue(v, s.fmt)] })}
                />
              ))}
              <path
                d={`M${left + x(s.ours)},${yMid - 8}l7,8l-7,8l-7,-8z`}
                fill="var(--cat-1)"
                stroke="var(--ink)"
                strokeWidth={0.8}
                onMouseEnter={() => setTip({ x: left + x(s.ours), y: yMid - 12, lines: [oursLabel, formatValue(s.ours, s.fmt)] })}
              />
            </g>
          );
        })}
      </svg>
      <p className="text-xs text-ink2 flex gap-4">
        <span>
          <span aria-hidden="true" style={{ color: "var(--cat-1)" }}>
            ◆
          </span>{" "}
          {oursLabel}
        </span>
        <span>
          <span aria-hidden="true" style={{ color: "var(--cat-2)" }}>
            ●
          </span>{" "}
          Real FDIC insured peers
        </span>
      </p>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
