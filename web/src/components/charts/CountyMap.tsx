"use client";

import { geoMercator, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { useEffect, useMemo, useState } from "react";

import { formatValue } from "@/lib/format";

import { Tooltip, type Tip } from "./Tooltip";
import { SEQUENTIAL, useWidth } from "./useWidth";

export interface CountyValue {
  fips: string;
  name: string;
  values: Record<string, number>;
}

type Props = { name: string };

/**
 * Counties on the sequential ramp, with a toggle between measures. The steps are the
 * ramp's seven colours over the range of the chosen measure, each county also prints
 * its value on hover, and the reference value is marked on the legend.
 */
export function CountyMap({
  base,
  counties,
  measures,
  reference,
}: {
  base: string;
  counties: CountyValue[];
  measures: { key: string; label: string; fmt: string }[];
  reference: { label: string; value: number; fmt: string };
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [shapes, setShapes] = useState<FeatureCollection<Geometry, Props> | null>(null);
  const [measure, setMeasure] = useState(measures[0]?.key ?? "");
  const [tip, setTip] = useState<Tip | null>(null);
  useEffect(() => {
    fetch(`${base}/data/nj_counties.json`)
      .then((r) => r.json() as Promise<FeatureCollection<Geometry, Props>>)
      .then(setShapes)
      .catch(() => setShapes(null));
  }, [base]);
  const byFips = useMemo(() => new Map(counties.map((c) => [c.fips, c])), [counties]);
  const chosen = measures.find((m) => m.key === measure) ?? measures[0];
  const values = counties.map((c) => c.values[measure] ?? 0);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const step = (v: number) => {
    const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
    return SEQUENTIAL[Math.min(SEQUENTIAL.length - 1, Math.floor(t * SEQUENTIAL.length))] ?? SEQUENTIAL[0];
  };
  const height = Math.min(520, Math.max(320, width * 1.15));
  const path = useMemo(() => {
    if (!shapes) return null;
    const projection = geoMercator().fitSize([Math.max(width - 8, 100), height - 8], shapes);
    return geoPath(projection);
  }, [shapes, width, height]);
  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <div className="flex flex-wrap gap-2 mb-2 text-xs" role="group" aria-label="Measure">
        {measures.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => setMeasure(m.key)}
            aria-pressed={measure === m.key}
            className={`px-2 py-0.5 rounded border ${measure === m.key ? "border-accent text-ink" : "border-hairline text-ink2"}`}
            data-testid={`measure-${m.key}`}
          >
            {m.label}
          </button>
        ))}
      </div>
      {path && shapes ? (
        <svg width={width} height={height} role="img" aria-label={`${chosen?.label ?? ""} by county`}>
          <g transform="translate(4,4)">
            {shapes.features.map((f: Feature<Geometry, Props>) => {
              const fips = String(f.id);
              const c = byFips.get(fips);
              const v = c?.values[measure];
              const d = path(f) ?? "";
              const show = () => {
                const [cx, cy] = path.centroid(f);
                setTip({ x: cx, y: cy, lines: [`${c?.name ?? f.properties.name} County`, `${chosen?.label}: ${formatValue(v ?? null, chosen?.fmt ?? "pct1")}`] });
              };
              return (
                <path
                  key={fips}
                  d={d}
                  fill={v === undefined ? "var(--surface)" : step(v)}
                  stroke="var(--surface)"
                  strokeWidth={1.2}
                  onMouseEnter={show}
                  onFocus={show}
                  tabIndex={0}
                  aria-label={`${c?.name ?? f.properties.name}: ${formatValue(v ?? null, chosen?.fmt ?? "pct1")}`}
                />
              );
            })}
          </g>
        </svg>
      ) : (
        <div className="skeleton rounded" style={{ height }} />
      )}
      <div className="flex items-center gap-2 text-xs text-ink2 mt-1" aria-label="Legend">
        <span className="num">{formatValue(lo, chosen?.fmt ?? "pct1")}</span>
        <span className="flex">
          {SEQUENTIAL.map((c) => (
            <span key={c} style={{ background: c, width: 22, height: 10, display: "inline-block" }} />
          ))}
        </span>
        <span className="num">{formatValue(hi, chosen?.fmt ?? "pct1")}</span>
        <span className="ml-3">
          {reference.label}: <span className="num">{formatValue(reference.value, reference.fmt)}</span>
        </span>
      </div>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
