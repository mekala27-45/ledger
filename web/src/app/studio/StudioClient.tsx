"use client";

import { type KeyboardEvent, type PointerEvent, useMemo, useRef, useState } from "react";

import { useWidth } from "@/components/charts/useWidth";
import { formatValue } from "@/lib/format";

import {
  type Card,
  type Characteristic,
  coarsen,
  type FineBin,
  fittedEdges,
  monotone,
  type Scored,
  scoreApplicant,
} from "./scorecard";

type Source = "api" | "browser";

function typical(c: Characteristic, fine: FineBin[] | undefined): string {
  if (c.kind === "categorical") {
    const biggest = [...c.bins].sort((a, b) => b.goods + b.bads - (a.goods + a.bads))[0];
    return biggest?.categories[0] ?? "";
  }
  const bins = (fine ?? []).filter((b) => !b.missing);
  const total = bins.reduce((s, b) => s + b.goods + b.bads, 0);
  let seen = 0;
  for (const b of bins) {
    seen += b.goods + b.bads;
    if (seen >= total / 2 && b.upper !== null) return String(b.upper);
  }
  return String(c.bins[0]?.upper ?? "");
}

export function StudioClient({
  card,
  fine,
  reasonText,
  minShare,
  ivFloor,
  apiUrl,
  notADecision,
}: {
  card: Card;
  fine: Record<string, FineBin[]>;
  reasonText: Record<string, string>;
  minShare: number;
  ivFloor: number;
  apiUrl: string;
  notADecision: string;
}) {
  const kept = card.characteristics;
  const editable = useMemo(
    () => [
      ...kept.filter((c) => c.kind === "numeric" && fine[c.name]).map((c) => c.name),
      ...Object.keys(card.dropped).filter((n) => fine[n]),
    ],
    [kept, fine, card.dropped],
  );
  const byName = useMemo(() => Object.fromEntries(kept.map((c) => [c.name, c])), [kept]);
  const fitted = useMemo(() => {
    const out: Record<string, number[]> = {};
    for (const name of editable) {
      const c = byName[name];
      const bins = fine[name] ?? [];
      // A dropped characteristic has no fitted coarse bins to start from: every fine edge is open.
      out[name] = c ? fittedEdges(c, bins) : bins.slice(0, -1).map((_, i) => i);
    }
    return out;
  }, [editable, byName, fine]);

  const [selected, setSelected] = useState(editable[0] ?? "");
  const [edges, setEdges] = useState<Record<string, number[]>>(fitted);
  const [active, setActive] = useState<number | null>(null);
  const dragging = useRef<number | null>(null);
  const [ref, width] = useWidth<HTMLDivElement>();

  const c = byName[selected];
  const fineBins = (fine[selected] ?? []).filter((b) => !b.missing);
  const current = [...(edges[selected] ?? [])].sort((a, b) => a - b);
  const coefficient = c?.coefficient ?? 0;
  const coarse = useMemo(
    () => coarsen(card, coefficient, fine[selected] ?? [], current),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [card, coefficient, fine, selected, current.join(",")],
  );
  const iv = coarse.reduce((s, b) => s + b.iv, 0);
  const fittedIv = card.iv[selected];
  const mono = monotone(coarse);
  const thin = coarse.filter((b) => b.share < minShare);
  const changed = current.join(",") !== [...(fitted[selected] ?? [])].sort((a, b) => a - b).join(",");

  const pad = { left: 44, right: 12, top: 14, bottom: 40 };
  const h = 230;
  const innerW = Math.max(width - pad.left - pad.right, 160);
  const innerH = h - pad.top - pad.bottom;
  const step = fineBins.length ? innerW / fineBins.length : innerW;
  const rates = fineBins.map((b) => (b.goods + b.bads ? b.bads / (b.goods + b.bads) : 0));
  const maxRate = Math.max(...rates, 0.01) * 1.1;
  const group = (i: number) => current.filter((e) => e < i).length;
  const boundaryX = (i: number) => pad.left + (i + 1) * step;

  const setFor = (name: string, next: number[]) => setEdges((prev) => ({ ...prev, [name]: next }));
  const moveEdge = (from: number, to: number) => {
    if (to < 0 || to > fineBins.length - 2 || current.includes(to)) return;
    setFor(
      selected,
      current.map((e) => (e === from ? to : e)),
    );
    setActive(to);
  };
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    if (dragging.current === null) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * width;
    const to = Math.round((x - pad.left) / step) - 1;
    if (to !== dragging.current) {
      const from = dragging.current;
      if (to >= 0 && to <= fineBins.length - 2 && !current.includes(to)) {
        dragging.current = to;
        moveEdge(from, to);
      }
    }
  };
  const onHandleKey = (e: KeyboardEvent<SVGGElement>, edge: number) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const dir = e.key === "ArrowLeft" ? -1 : 1;
      let to = edge + dir;
      while (current.includes(to)) to += dir;
      moveEdge(edge, to);
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      setFor(
        selected,
        current.filter((x) => x !== edge),
      );
      setActive(null);
    }
  };

  // The applicant form.
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(kept.map((k) => [k.name, typical(k, fine[k.name])])),
  );
  const [result, setResult] = useState<(Scored & { source: Source }) | null>(null);
  const [problem, setProblem] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const applicant = () =>
    Object.fromEntries(
      kept.map((k) => {
        const raw = form[k.name] ?? "";
        return [k.name, k.kind === "numeric" ? (raw === "" ? null : Number(raw)) : raw];
      }),
    ) as Record<string, string | number | null>;

  const score = async () => {
    setBusy(true);
    setProblem("");
    const body = applicant();
    try {
      if (apiUrl) {
        try {
          const r = await fetch(`${apiUrl}/v1/scorecard/score`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ applicant: body }),
            signal: AbortSignal.timeout(6000),
          });
          if (r.ok) {
            const j = (await r.json()) as {
              score: number;
              probability_of_default: number;
              decision: "approve" | "decline";
              points: Record<string, number>;
              reasons: string[];
            };
            setResult({
              score: j.score,
              probability: j.probability_of_default,
              decision: j.decision,
              points: j.points,
              reasons: j.reasons,
              source: "api",
            });
            return;
          }
        } catch {
          // Asleep or unreachable: score in the browser from the same file.
        }
      }
      setResult({ ...scoreApplicant(card, body, reasonText), source: "browser" });
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-10">
      <section aria-label="Bin a characteristic">
        <h2 className="font-serif text-2xl mb-1">Bin a characteristic</h2>
        <p className="text-sm text-ink2 mb-3 max-w-3xl">
          Drag a handle to move a coarse bin edge, click a gap between two bars to add one, or select a handle and press
          Delete to remove it. Arrow keys move a selected handle.
        </p>
        <div className="flex flex-wrap gap-2 mb-4" role="tablist" aria-label="Characteristic">
          {editable.map((name) => {
            const isKept = Boolean(byName[name]);
            return (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={name === selected}
                onClick={() => {
                  setSelected(name);
                  setActive(null);
                }}
                className={`px-2.5 py-1 rounded border text-xs font-mono ${
                  name === selected ? "border-accent text-ink" : "border-hairline text-ink2"
                } ${isKept ? "" : "opacity-70"}`}
                title={isKept ? `IV ${formatValue(card.iv[name] ?? null, "float3")}` : card.dropped[name]}
              >
                {name}
                {isKept ? "" : " (dropped)"}
              </button>
            );
          })}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
          <div className="xl:col-span-3 border border-hairline bg-raised rounded-md p-3">
            <div ref={ref} className="w-full">
              <svg
                width={width}
                height={h}
                role="img"
                aria-label={`Default rate by fine bin of ${selected}, with coarse bin edges`}
                onPointerMove={onPointerMove}
                onPointerUp={() => (dragging.current = null)}
                onPointerLeave={() => (dragging.current = null)}
                className="touch-none select-none"
                data-testid="bin-editor"
              >
                {[0, 0.5, 1].map((f) => (
                  <g key={f}>
                    <line x1={pad.left} x2={pad.left + innerW} y1={pad.top + innerH * (1 - f)} y2={pad.top + innerH * (1 - f)} stroke="var(--hairline)" />
                    <text x={pad.left - 6} y={pad.top + innerH * (1 - f)} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[10px] num">
                      {formatValue(maxRate * f, "pct1")}
                    </text>
                  </g>
                ))}
                {fineBins.map((b, i) => {
                  const r = rates[i] ?? 0;
                  const bh = (r / maxRate) * innerH;
                  const odd = group(i) % 2 === 1;
                  return (
                    <g key={i}>
                      <rect
                        x={pad.left + i * step + 1}
                        y={pad.top + innerH - bh}
                        width={Math.max(step - 2, 1)}
                        height={bh}
                        fill={odd ? "var(--cat-2)" : "var(--cat-1)"}
                        opacity={0.85}
                      >
                        <title>{`${b.lower ?? "-inf"} to ${b.upper ?? "+inf"}: ${formatValue(r, "pct2")} default, ${formatValue(b.goods + b.bads, "int")} loans`}</title>
                      </rect>
                      {odd ? (
                        <rect x={pad.left + i * step + 1} y={pad.top + innerH - bh} width={Math.max(step - 2, 1)} height={bh} fill="url(#hatch)" />
                      ) : null}
                    </g>
                  );
                })}
                <defs>
                  <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                    <line y2="5" stroke="var(--surface)" strokeWidth="1.2" opacity="0.5" />
                  </pattern>
                </defs>
                {fineBins.slice(0, -1).map((_, i) =>
                  current.includes(i) ? null : (
                    <rect
                      key={`gap-${i}`}
                      x={boundaryX(i) - 5}
                      y={pad.top}
                      width={10}
                      height={innerH}
                      fill="transparent"
                      className="cursor-copy"
                      onClick={() => {
                        setFor(selected, [...current, i]);
                        setActive(i);
                      }}
                    >
                      <title>Add an edge here</title>
                    </rect>
                  ),
                )}
                {current.map((edge) => (
                  <g
                    key={`edge-${edge}`}
                    transform={`translate(${boundaryX(edge)},0)`}
                    role="slider"
                    tabIndex={0}
                    aria-label={`Coarse bin edge at ${fineBins[edge]?.upper ?? ""}`}
                    aria-valuemin={0}
                    aria-valuemax={fineBins.length - 2}
                    aria-valuenow={edge}
                    aria-valuetext={String(fineBins[edge]?.upper ?? "")}
                    onKeyDown={(e) => onHandleKey(e, edge)}
                    onFocus={() => setActive(edge)}
                    onPointerDown={(e) => {
                      (e.currentTarget.ownerSVGElement ?? e.currentTarget).setPointerCapture?.(e.pointerId);
                      dragging.current = edge;
                      setActive(edge);
                    }}
                    className="cursor-ew-resize outline-none"
                    data-testid="edge-handle"
                  >
                    <line y1={pad.top - 4} y2={pad.top + innerH} stroke={active === edge ? "var(--accent)" : "var(--ink)"} strokeWidth={active === edge ? 2.5 : 1.5} />
                    <rect x={-5} y={pad.top - 12} width={10} height={14} rx={2} fill={active === edge ? "var(--accent)" : "var(--ink)"} />
                    <rect x={-8} y={pad.top - 12} width={16} height={innerH + 12} fill="transparent" />
                  </g>
                ))}
                {fineBins.map((b, i) =>
                  i % Math.max(1, Math.ceil(fineBins.length / 10)) === 0 && b.upper !== null ? (
                    <text key={`t-${i}`} x={pad.left + (i + 1) * step} y={pad.top + innerH + 14} textAnchor="middle" className="fill-[var(--ink2)] text-[10px] font-mono">
                      {Math.abs(b.upper) >= 1000 ? `${Math.round(b.upper / 1000)}k` : Number(b.upper.toPrecision(3))}
                    </text>
                  ) : null,
                )}
                <text x={pad.left + innerW / 2} y={h - 6} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
                  {selected}, fine bins in order (upper edge)
                </text>
              </svg>
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-2 text-xs">
              <button
                type="button"
                disabled={!changed}
                onClick={() => {
                  setFor(selected, fitted[selected] ?? []);
                  setActive(null);
                }}
                className="px-2 py-0.5 border border-hairline rounded disabled:opacity-40"
              >
                Reset to the fitted bins
              </button>
              <span className="text-ink2">{changed ? "Your bins" : "The pipeline's bins"}</span>
            </div>
          </div>

          <div className="xl:col-span-2 space-y-3" aria-live="polite">
            <div className="grid grid-cols-3 gap-2">
              <div className="border border-hairline bg-raised rounded-md px-3 py-2">
                <div className="text-xs text-ink2">Information value</div>
                <div className="text-xl num text-left" data-testid="iv">
                  {formatValue(iv, "float3")}
                </div>
                <div className="text-xs text-ink2">
                  {fittedIv !== undefined ? `fitted ${formatValue(fittedIv, "float3")}` : ""}
                  {iv < ivFloor ? ` · below the floor ${formatValue(ivFloor, "float2")}` : ""}
                </div>
              </div>
              <div className="border border-hairline bg-raised rounded-md px-3 py-2">
                <div className="text-xs text-ink2">Monotone</div>
                <div className={`text-xl ${mono.ok ? "text-good" : "text-critical"}`} data-testid="monotone">
                  {mono.ok ? "✓ yes" : "✕ no"}
                </div>
                <div className="text-xs text-ink2">
                  {mono.ok
                    ? `WoE ${mono.direction} with the value`
                    : `reverses at bin ${mono.breaks.map((b) => b + 1).join(", ")}`}
                </div>
              </div>
              <div className="border border-hairline bg-raised rounded-md px-3 py-2">
                <div className="text-xs text-ink2">Bins</div>
                <div className="text-xl num text-left">{coarse.length}</div>
                <div className={`text-xs ${thin.length ? "text-warning" : "text-ink2"}`}>
                  {thin.length
                    ? `⚠ ${thin.length} under ${formatValue(minShare, "pct0")} of loans`
                    : `none under ${formatValue(minShare, "pct0")}`}
                </div>
              </div>
            </div>
            <div className="border border-hairline bg-raised rounded-md p-3 overflow-x-auto">
              <table className="data-table w-full" data-testid="coarse-table">
                <thead>
                  <tr>
                    <th>Bin</th>
                    <th className="num">Share</th>
                    <th className="num">Default</th>
                    <th className="num">WoE</th>
                    <th className="num">IV</th>
                    <th className="num">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {coarse.map((b, i) => (
                    <tr key={b.label} className={mono.breaks.includes(i) ? "text-critical" : ""}>
                      <td className="font-mono whitespace-nowrap">{b.label}</td>
                      <td className={`num ${b.share < minShare ? "text-warning" : ""}`}>{formatValue(b.share, "pct1")}</td>
                      <td className="num">{formatValue(b.badRate, "pct2")}</td>
                      <td className="num">{formatValue(b.woe, "float3")}</td>
                      <td className="num">{formatValue(b.iv, "float3")}</td>
                      <td className="num">{c ? formatValue(b.points, "float1") : "not in the card"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-ink2 mt-2">
                {c
                  ? `Points are at the coefficient fitted on the pipeline's bins (${formatValue(coefficient, "float3")}). Moving an edge changes the weight of evidence and so the points; the coefficient is refit only when the pipeline runs with new bins.`
                  : `Dropped from the scorecard: ${card.dropped[selected] ?? ""}. Its weight of evidence and information value still update here.`}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section aria-label="Score an applicant">
        <h2 className="font-serif text-2xl mb-1">Score an applicant</h2>
        <p className="text-sm text-ink2 mb-3 max-w-3xl">
          The API scores the application when it is awake; otherwise the browser scores it from the same published
          scorecard file, and the result says which. Protected attributes and their listed proxies are not on the form
          because the scorecard cannot use them.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <form
            className="border border-hairline bg-raised rounded-md p-4 grid grid-cols-1 sm:grid-cols-2 gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void score();
            }}
            data-testid="applicant-form"
          >
            {kept.map((k) => (
              <label key={k.name} className="text-xs text-ink2 flex flex-col gap-1">
                <span className="font-mono">{k.name}</span>
                {k.kind === "categorical" ? (
                  <select
                    value={form[k.name] ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, [k.name]: e.target.value }))}
                    className="bg-surface border border-hairline rounded px-2 py-1 text-sm text-ink"
                  >
                    {k.bins.flatMap((b) => b.categories).map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    step="any"
                    value={form[k.name] ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, [k.name]: e.target.value }))}
                    className="bg-surface border border-hairline rounded px-2 py-1 text-sm text-ink num text-left"
                    name={k.name}
                  />
                )}
              </label>
            ))}
            <div className="sm:col-span-2 flex items-center gap-3">
              <button type="submit" disabled={busy} className="px-3 py-1.5 rounded bg-accent text-surface text-sm font-semibold disabled:opacity-50">
                {busy ? "Scoring…" : "Score"}
              </button>
              <button
                type="button"
                className="text-xs underline text-ink2"
                onClick={() => setForm(Object.fromEntries(kept.map((k) => [k.name, typical(k, fine[k.name])])))}
              >
                Typical applicant
              </button>
            </div>
          </form>

          <div className="border border-hairline bg-raised rounded-md p-4" aria-live="polite" data-testid="applicant-result">
            {problem ? <p className="text-critical text-sm">{problem}</p> : null}
            {result ? (
              <>
                <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
                  <div>
                    <div className="text-xs text-ink2">Score</div>
                    <div className="text-3xl num text-left" data-testid="score">
                      {formatValue(result.score, "float1")}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-ink2">Probability of default</div>
                    <div className="text-xl num text-left">{formatValue(result.probability, "pct2")}</div>
                  </div>
                  <div>
                    <div className="text-xs text-ink2">At the cutoff of {formatValue(card.cutoff, "int")}</div>
                    <div className={`text-xl font-semibold ${result.decision === "approve" ? "text-good" : "text-critical"}`} data-testid="decision">
                      {result.decision === "approve" ? "✓ approve" : "✕ decline"}
                    </div>
                  </div>
                </div>
                {result.reasons.length ? (
                  <div className="mt-3">
                    <div className="text-xs text-ink2">Principal reasons, in the order the notice would list them</div>
                    <ol className="list-decimal pl-5 text-sm mt-1 space-y-0.5" data-testid="reasons">
                      {result.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                <table className="data-table w-full mt-3">
                  <thead>
                    <tr>
                      <th>Characteristic</th>
                      <th className="num">Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.points).map(([name, pts]) => (
                      <tr key={name}>
                        <td className="font-mono">{name}</td>
                        <td className="num">{formatValue(pts, "float1")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-ink2 mt-3">
                  {result.source === "api" ? "Scored by the API." : "Scored in your browser from the published scorecard file; the API is asleep."}{" "}
                  {notADecision}
                </p>
              </>
            ) : (
              <p className="text-sm text-ink2">Fill in the form and press Score.</p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
