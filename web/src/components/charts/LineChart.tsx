"use client";

import { scaleLinear, scalePoint } from "d3-scale";
import { line } from "d3-shape";
import { useMemo, useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { DASHES, SERIES, useWidth } from "./useWidth";

export interface Series {
  name: string;
  points: { x: number | string; y: number | null }[];
  color?: string;
  dash?: string;
  band?: { x: number | string; low: number | null; high: number | null }[];
  emphasis?: boolean;
  /** Series with the same legend text share one legend entry, drawn in the first one's style. */
  legend?: string;
}

export interface Marker {
  x: number | string;
  label: string;
  color?: string;
}

/**
 * Lines on one axis. Up to eight series are labelled directly at their right end;
 * beyond that a legend takes over. Each series has its own dash pattern as well as its
 * own hue, so it survives greyscale printing and colour vision deficiency.
 */
export function LineChart({
  series,
  yFormat,
  xLabel,
  yLabel,
  markers = [],
  height = 280,
  xFormat,
  yDomain,
  points = false,
}: {
  series: Series[];
  yFormat: string;
  xLabel: string;
  yLabel: string;
  markers?: Marker[];
  height?: number;
  /** A format name for numeric x values, or "log10" when x is the base ten logarithm of the quantity. */
  xFormat?: string;
  yDomain?: [number, number];
  points?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const direct = series.length <= 8;
  const margin = { top: 12, right: direct ? 118 : 16, bottom: 38, left: 58 };
  const innerW = Math.max(width - margin.left - margin.right, 120);
  const innerH = height - margin.top - margin.bottom;
  const allX = useMemo(() => {
    const xs = series.flatMap((s) => s.points.map((p) => p.x));
    const numeric = xs.every((x) => typeof x === "number");
    return numeric ? Array.from(new Set(xs as number[])).sort((a, b) => a - b) : Array.from(new Set(xs.map(String))).sort();
  }, [series]);
  const numericX = allX.every((x) => typeof x === "number");
  const x = useMemo(() => {
    if (numericX) {
      const xs = allX as number[];
      return (v: number | string) =>
        scaleLinear()
          .domain([xs[0] ?? 0, xs[xs.length - 1] ?? 1])
          .range([0, innerW])(Number(v));
    }
    const s = scalePoint<string>().domain(allX as string[]).range([0, innerW]);
    return (v: number | string) => s(String(v)) ?? 0;
  }, [allX, numericX, innerW]);
  const ys = series.flatMap((s) => [
    ...s.points.map((p) => p.y),
    ...(s.band ?? []).flatMap((b) => [b.low, b.high]),
  ]).filter((v): v is number => v !== null && Number.isFinite(v));
  const lo = yDomain ? yDomain[0] : Math.min(0, ...ys);
  const hi = yDomain ? yDomain[1] : Math.max(...ys, 0) * 1.05 || 1;
  const y = scaleLinear().domain([lo, hi]).nice().range([innerH, 0]);
  const ticks = y.ticks(5);
  const xLo = Number(allX[0] ?? 0);
  const xHi = Number(allX[allX.length - 1] ?? 1);
  const xTicks = !numericX
    ? (allX as string[]).filter((_, i, arr) => i % Math.max(1, Math.ceil(arr.length / 8)) === 0)
    : xFormat === "log10"
      ? Array.from({ length: Math.floor(xHi) - Math.ceil(xLo) + 1 }, (_, i) => Math.ceil(xLo) + i)
      : scaleLinear().domain([xLo, xHi]).ticks(6);
  const fmtX = (v: number | string): string => {
    if (xFormat === "log10") {
      const t = 10 ** Number(v);
      return t < 0.001 ? t.toExponential(0) : String(Number(t.toPrecision(2)));
    }
    return xFormat ? formatValue(Number(v), xFormat) : String(v);
  };
  const path = line<{ x: number | string; y: number | null }>()
    .defined((d) => d.y !== null && Number.isFinite(d.y))
    .x((d) => x(d.x))
    .y((d) => y(d.y ?? 0));

  // Direct labels at each line's last point, pushed apart so two lines ending close together
  // never print on top of each other.
  const GAP = 13;
  const labels = series
    .map((s, i) => {
      const last = [...s.points].reverse().find((p) => p.y !== null && Number.isFinite(p.y));
      return last ? { name: s.name, x: x(last.x), y: y(last.y ?? 0), color: s.color ?? SERIES[i % SERIES.length] ?? "var(--ink)" } : null;
    })
    .filter((l): l is { name: string; x: number; y: number; color: string } => l !== null)
    .sort((a, b) => a.y - b.y);
  for (let pass = 0; pass < 20; pass += 1) {
    let moved = false;
    for (let i = 1; i < labels.length; i += 1) {
      const above = labels[i - 1];
      const here = labels[i];
      if (above && here && here.y - above.y < GAP) {
        const push = (GAP - (here.y - above.y)) / 2;
        above.y -= push;
        here.y += push;
        moved = true;
      }
    }
    for (const l of labels) l.y = Math.min(Math.max(l.y, 4), innerH + 6);
    if (!moved) break;
  }

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg width={width} height={height} role="img" aria-label={`${yLabel} by ${xLabel}`}>
        <g transform={`translate(${margin.left},${margin.top})`}>
          {ticks.map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x2={innerW} stroke="var(--hairline)" />
              <text x={-8} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[11px] num">
                {formatValue(t, yFormat)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={String(t)} x={x(t)} y={innerH + 18} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
              {fmtX(t)}
            </text>
          ))}
          <text x={innerW / 2} y={innerH + 34} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
            {xLabel}
          </text>
          {series.map((s, i) =>
            s.band ? (
              <path
                key={`band-${s.name}`}
                d={
                  "M" +
                  s.band.filter((b) => b.low !== null && b.high !== null).map((b) => `${x(b.x)},${y(b.high ?? 0)}`).join("L") +
                  "L" +
                  [...s.band]
                    .filter((b) => b.low !== null && b.high !== null)
                    .reverse()
                    .map((b) => `${x(b.x)},${y(b.low ?? 0)}`)
                    .join("L") +
                  "Z"
                }
                fill={s.color ?? SERIES[i % SERIES.length]}
                opacity={0.12}
              />
            ) : null,
          )}
          {markers.map((m) => (
            <g key={m.label} transform={`translate(${x(m.x)},0)`}>
              <line y2={innerH} stroke={m.color ?? "var(--control)"} strokeDasharray="3 3" />
              <text y={-2} x={4} className="fill-[var(--ink2)] text-[10px]">
                {m.label}
              </text>
            </g>
          ))}
          {series.map((s, i) => (
            <path
              key={s.name}
              d={path(s.points) ?? ""}
              fill="none"
              stroke={s.color ?? SERIES[i % SERIES.length]}
              strokeWidth={s.emphasis ? 2.6 : 1.6}
              strokeDasharray={s.dash ?? DASHES[i % DASHES.length]}
            />
          ))}
          {series.map((s, i) =>
            s.points
              .filter((p) => p.y !== null && Number.isFinite(p.y))
              .map((p) => (
                <circle
                  key={`${s.name}-${String(p.x)}`}
                  cx={x(p.x)}
                  cy={y(p.y ?? 0)}
                  r={points ? 2.6 : 7}
                  fill={points ? (s.color ?? SERIES[i % SERIES.length]) : "transparent"}
                  onMouseEnter={() =>
                    setTip({ x: x(p.x) + margin.left, y: y(p.y ?? 0), lines: [s.name, `${fmtX(p.x)}: ${formatValue(p.y, yFormat)}`] })
                  }
                  onFocus={() =>
                    setTip({ x: x(p.x) + margin.left, y: y(p.y ?? 0), lines: [s.name, `${fmtX(p.x)}: ${formatValue(p.y, yFormat)}`] })
                  }
                />
              )),
          )}
          {direct
            ? labels.map((l) => (
                <text key={`label-${l.name}`} x={l.x + 6} y={l.y} dy="0.32em" className="text-[11px]" fill={l.color}>
                  {l.name}
                </text>
              ))
            : null}
        </g>
      </svg>
      {!direct ? (
        <ul className="flex flex-wrap gap-3 text-xs text-ink2 mt-1" aria-label="Legend">
          {series
            .map((s, i) => ({ s, i, text: s.legend ?? s.name }))
            .filter((e, k, all) => all.findIndex((o) => o.text === e.text) === k)
            .map(({ s, i, text }) => (
              <li key={text} className="flex items-center gap-1">
                <svg width="18" height="8" aria-hidden="true">
                  <line
                    x2="18"
                    y1="4"
                    y2="4"
                    stroke={s.color ?? SERIES[i % SERIES.length]}
                    strokeWidth={s.emphasis ? 2.6 : 2}
                    strokeDasharray={s.dash ?? DASHES[i % DASHES.length]}
                  />
                </svg>
                {text}
              </li>
            ))}
        </ul>
      ) : null}
      <p className="sr-only">{yLabel}</p>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
