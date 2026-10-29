"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { formatValue } from "@/lib/format";

interface DeskEvent {
  txn_id: number;
  time: string;
  card: string;
  category: string;
  amount: number;
  distance_km: number;
  lat: number;
  lon: number;
  score: number;
  decision: "approve" | "review" | "decline";
  queue: boolean;
  rules: string[];
  reasons: string;
}
interface Panel {
  clock: string;
  decisions: number;
  labelled: number;
  unlabelled: number;
  precision: number | null;
  recall: number | null;
}
interface Recorded {
  start: string;
  hours: number;
  operating_point: number;
  queue_point: number;
  chargeback_days: number;
  events: DeskEvent[];
  panels: Panel[];
}
interface HistBin {
  bin: number;
  n: number;
  frauds: number;
  fraud_amount: number;
  lower: number;
}

const SPEEDS = [0.25, 1, 4, 16];
const TICK_MS = 100;
const FEED = 36;
const MAP_POINTS = 400;
// The continental United States, for Sparkov's merchant coordinates.
const LON: [number, number] = [-125, -66];
const LAT: [number, number] = [24, 50];

/** The stream's timestamps carry no zone; read them as UTC so the clock shows them unchanged. */
function utc(stamp: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(stamp) ? stamp : `${stamp}Z`);
}

function decisionMark(d: DeskEvent["decision"]) {
  if (d === "decline") return <span className="text-critical font-semibold">✕ decline</span>;
  if (d === "review") return <span className="text-warning font-semibold">▲ review</span>;
  return <span className="text-ink2">· approve</span>;
}

export function DeskClient({
  base,
  apiUrl,
  costFalseDecline,
  costHandling,
}: {
  base: string;
  apiUrl: string;
  costFalseDecline: number;
  costHandling: number;
}) {
  const [recorded, setRecorded] = useState<Recorded | null>(null);
  const [hist, setHist] = useState<HistBin[]>([]);
  const [mode, setMode] = useState<"connecting" | "live" | "recorded">("connecting");
  const [speed, setSpeed] = useState(1);
  const [clock, setClock] = useState<number>(0);
  const [cursor, setCursor] = useState(0);
  const [liveEvents, setLiveEvents] = useState<DeskEvent[]>([]);
  const [livePanel, setLivePanel] = useState<Panel | null>(null);
  const [liveClock, setLiveClock] = useState<string>("");
  const [threshold, setThreshold] = useState<number | null>(null);
  const started = useRef<{ real: number; sim: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(`${base}/data/f04/replay_recorded.json`).then((r) => r.json() as Promise<Recorded>),
      fetch(`${base}/data/f04/score_histogram.json`).then((r) => r.json() as Promise<HistBin[]>),
    ])
      .then(([rec, h]) => {
        if (cancelled) return;
        setRecorded(rec);
        setHist(h);
        setThreshold(rec.operating_point);
      })
      .catch(() => setMode("recorded"));
    return () => {
      cancelled = true;
    };
  }, [base]);

  // Try the live stream; fall back to the recorded replay if it does not answer.
  // The host scales the API to zero, so the first request wakes it: the health probe waits for
  // that before the stream opens. The host also ends every request after a few minutes, so the
  // API closes each stream on a timer with an `end` event, and the desk reconnects to the same
  // replay. A stream that drops after it was live is reopened a few times before giving up.
  useEffect(() => {
    if (!recorded) return;
    // The end to end tests point the desk at a mocked API without a second build.
    const api = (window as { __ledgerApiForTests?: string }).__ledgerApiForTests ?? apiUrl;
    if (!api) {
      setMode("recorded");
      return;
    }
    let stopped = false;
    let everLive = false;
    let retries = 0;
    let source: EventSource | null = null;
    let timer: number | undefined;
    let retryTimer: number | undefined;

    const fallback = () => {
      if (!stopped) setMode("recorded");
    };
    const reopen = () => {
      if (stopped) return;
      if (retries >= 3) {
        fallback();
        return;
      }
      retries += 1;
      retryTimer = window.setTimeout(() => open(), 1000 * retries);
    };
    const open = () => {
      if (stopped) return;
      let settled = false;
      const stream = new EventSource(`${api}/v1/desk/stream?batch_ms=250`);
      source = stream;
      timer = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        stream.close();
        if (everLive) reopen();
        else fallback();
      }, 15000);
      stream.addEventListener("hello", () => {
        settled = true;
        window.clearTimeout(timer);
        everLive = true;
        retries = 0;
        setMode("live");
      });
      stream.addEventListener("transactions", (e) => {
        const message = JSON.parse((e as MessageEvent<string>).data) as {
          events: DeskEvent[];
          desk?: { clock: string | null; labelled: Panel | null };
        };
        setLiveEvents((prev) => [...prev, ...message.events].slice(-MAP_POINTS));
        if (message.desk?.labelled) setLivePanel(message.desk.labelled);
        if (message.desk?.clock) setLiveClock(message.desk.clock);
      });
      stream.addEventListener("end", () => {
        settled = true;
        window.clearTimeout(timer);
        stream.close();
        retries = 0;
        reopen();
      });
      stream.onerror = () => {
        window.clearTimeout(timer);
        stream.close();
        const wasSettled = settled;
        settled = true;
        if (everLive) reopen();
        else if (!wasSettled) fallback();
      };
    };

    const wake = new AbortController();
    const wakeTimer = window.setTimeout(() => wake.abort(), 20000);
    fetch(`${api}/v1/health`, { signal: wake.signal })
      .then((r) => {
        if (r.ok) open();
        else fallback();
      })
      .catch(() => fallback())
      .finally(() => window.clearTimeout(wakeTimer));
    return () => {
      stopped = true;
      wake.abort();
      window.clearTimeout(wakeTimer);
      window.clearTimeout(timer);
      window.clearTimeout(retryTimer);
      source?.close();
    };
  }, [recorded, apiUrl]);

  // The recorded replay's clock: one simulated hour per real second at speed 1.
  useEffect(() => {
    if (mode !== "recorded" || !recorded) return;
    const start = utc(recorded.start);
    const end = start + recorded.hours * 3600 * 1000;
    started.current = { real: performance.now(), sim: clock || start };
    const timer = window.setInterval(() => {
      const s = started.current;
      if (!s) return;
      const elapsed = (performance.now() - s.real) / 1000;
      let sim = s.sim + elapsed * speed * 3600 * 1000;
      if (sim >= end) {
        sim = start;
        started.current = { real: performance.now(), sim: start };
      }
      setClock(sim);
    }, TICK_MS);
    return () => window.clearInterval(timer);
    // The clock is read once when the speed or mode changes, deliberately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, recorded, speed]);

  useEffect(() => {
    if (!recorded) return;
    const events = recorded.events;
    let lo = 0;
    let hi = events.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (utc(events[mid]?.time ?? "") <= clock) lo = mid + 1;
      else hi = mid;
    }
    setCursor(lo);
  }, [clock, recorded]);

  const shown: DeskEvent[] = useMemo(() => {
    if (mode === "live") return liveEvents;
    if (!recorded) return [];
    return recorded.events.slice(Math.max(0, cursor - MAP_POINTS), cursor);
  }, [mode, liveEvents, recorded, cursor]);

  const counts = useMemo(() => {
    const c = { approve: 0, review: 0, decline: 0 };
    const source = mode === "live" ? liveEvents : recorded?.events.slice(0, cursor) ?? [];
    for (const e of source) c[e.decision] += 1;
    return c;
  }, [mode, liveEvents, recorded, cursor]);
  const total = counts.approve + counts.review + counts.decline;

  const panel = useMemo(() => {
    if (mode === "live") return livePanel;
    if (!recorded) return null;
    const hour = Math.floor((clock - utc(recorded.start)) / 3600000);
    return recorded.panels[Math.max(0, Math.min(recorded.panels.length - 1, hour))] ?? null;
  }, [clock, recorded, mode, livePanel]);

  const alerts = useMemo(
    () =>
      shown
        .filter((e) => e.decision !== "approve")
        .sort((a, b) => Number(b.queue) - Number(a.queue) || b.score - a.score)
        .slice(0, 12),
    [shown],
  );

  const slider = useMemo(() => {
    if (!hist.length || threshold === null) return null;
    const frauds = hist.reduce((s, b) => s + b.frauds, 0);
    const fraudAmount = hist.reduce((s, b) => s + b.fraud_amount, 0);
    const at = (t: number) => {
      const flagged = hist.filter((b) => b.lower >= t);
      const tp = flagged.reduce((s, b) => s + b.frauds, 0);
      const fp = flagged.reduce((s, b) => s + (b.n - b.frauds), 0);
      const caughtAmount = flagged.reduce((s, b) => s + b.fraud_amount, 0);
      const missed = frauds - tp;
      const cost = fp * costFalseDecline + (fraudAmount - caughtAmount) + missed * costHandling;
      return { precision: tp + fp ? tp / (tp + fp) : null, recall: frauds ? tp / frauds : null, cost, flagged: tp + fp };
    };
    const points = hist.map((b) => b.lower).filter((v) => v > 0);
    const costs = points.map((p) => ({ t: p, ...at(p) }));
    const best = costs.reduce((a, b) => (b.cost < a.cost ? b : a), costs[0] ?? { t: 0, ...at(0) });
    return { current: at(threshold), best, points };
  }, [hist, threshold, costFalseDecline, costHandling]);

  const mapW = 640;
  const mapH = 300;
  const px = (lon: number) => ((lon - LON[0]) / (LON[1] - LON[0])) * mapW;
  const py = (lat: number) => mapH - ((lat - LAT[0]) / (LAT[1] - LAT[0])) * mapH;
  const clockLabel =
    mode === "live"
      ? liveClock.replace("T", " ").slice(0, 16)
      : clock
        ? new Date(clock).toISOString().replace("T", " ").slice(0, 16)
        : "";

  return (
    <div className="space-y-4">
      <div
        className={`rounded-md border px-3 py-2 text-sm ${mode === "live" ? "border-good text-good" : "border-warning text-warning"}`}
        role="status"
        data-testid="desk-mode"
      >
        {mode === "live" && (
          <>● Live: the API is replaying the scored stream and scoring as it goes. Simulated clock {clockLabel}.</>
        )}
        {mode === "recorded" && (
          <>
            ▶ Recorded replay: the live API is not answering, so your browser is playing the same scored stream from a file.
            Simulated clock {clockLabel}.
          </>
        )}
        {mode === "connecting" && (
          <>Connecting to the desk. The API sleeps when nobody is watching, so the first visit can take a few seconds.</>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm no-print">
        <span className="text-ink2">Replay speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              started.current = null;
              setSpeed(s);
            }}
            aria-pressed={speed === s}
            className={`px-2 py-0.5 rounded border ${speed === s ? "border-accent text-ink" : "border-hairline text-ink2"}`}
          >
            {s < 1 ? `${s * 60} min` : `${s} h`} per second
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {(["approve", "review", "decline"] as const).map((d) => (
          <div key={d} className="border border-hairline bg-raised rounded-md px-3 py-2">
            <div className="text-xs text-ink2">{d === "approve" ? "Approved" : d === "review" ? "Sent to review" : "Declined"}</div>
            <div className="text-xl num text-left">{total ? formatValue(counts[d] / total, "pct2") : "…"}</div>
            <div className="text-xs text-ink2 num text-left">{formatValue(counts[d], "int")} transactions</div>
          </div>
        ))}
        <div className="border border-hairline bg-raised rounded-md px-3 py-2 col-span-2" data-testid="late-labels">
          <div className="text-xs text-ink2">Precision and recall, labelled decisions only</div>
          <div className="text-xl num text-left">
            {panel ? `${formatValue(panel.precision, "pct1")} · ${formatValue(panel.recall, "pct1")}` : "…"}
          </div>
          <div className="text-xs text-ink2">
            {panel
              ? `${formatValue(panel.unlabelled, "int")} of ${formatValue(panel.decisions, "int")} decisions are still inside the ${recorded?.chargeback_days ?? 60} day chargeback window and count in neither.`
              : ""}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <section className="xl:col-span-3 border border-hairline bg-raised rounded-md" aria-label="Transaction feed">
          <h2 className="px-3 pt-3 text-sm font-semibold">The feed</h2>
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-[11.5px] leading-tight" data-testid="feed">
              <thead className="text-ink2">
                <tr>
                  <th className="text-left px-3 py-2 font-normal">Time</th>
                  <th className="text-left px-2 font-normal">Card</th>
                  <th className="text-left px-2 font-normal">Category</th>
                  <th className="num px-2 font-normal">Amount</th>
                  <th className="num px-2 font-normal">km</th>
                  <th className="num px-2 font-normal">Score</th>
                  <th className="text-left px-2 font-normal">Decision</th>
                  <th className="text-left px-2 font-normal hidden md:table-cell">Why</th>
                </tr>
              </thead>
              <tbody>
                {[...shown].slice(-FEED).reverse().map((e) => (
                  <tr key={e.txn_id} className="border-t border-hairline">
                    <td className="px-3 py-1 whitespace-nowrap">{e.time.slice(5, 16).replace("T", " ")}</td>
                    <td className="px-2">{e.card}</td>
                    <td className="px-2">{e.category}</td>
                    <td className="px-2 num">{e.amount.toFixed(2)}</td>
                    <td className="px-2 num">{e.distance_km.toFixed(0)}</td>
                    <td className="px-2 num">{e.score.toFixed(4)}</td>
                    <td className="px-2 whitespace-nowrap">{decisionMark(e.decision)}</td>
                    <td className="px-2 text-ink2 hidden md:table-cell">{[...e.rules, e.reasons].filter(Boolean).join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="xl:col-span-2 border border-hairline bg-raised rounded-md p-3" aria-label="Alert queue">
          <h2 className="text-sm font-semibold">The alert queue</h2>
          <p className="text-xs text-ink2 mb-2">
            Declines and reviews, the queue point ({recorded ? recorded.queue_point.toFixed(4) : "…"}) first, then by score.
          </p>
          <ul className="space-y-1 font-mono text-[11.5px]" data-testid="queue">
            {alerts.map((a) => (
              <li key={a.txn_id} className="flex justify-between gap-2 border-t border-hairline pt-1">
                <span>
                  {a.queue ? <span className="text-critical">★ queue </span> : null}
                  {a.card} {a.category}
                </span>
                <span className="num">
                  ${a.amount.toFixed(2)} · {a.score.toFixed(3)}
                </span>
              </li>
            ))}
            {!alerts.length ? <li className="text-ink2">No alerts in the window yet.</li> : null}
          </ul>
        </section>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <section className="border border-hairline bg-raised rounded-md p-3 hidden sm:block" aria-label="Map of recent transactions">
          <h2 className="text-sm font-semibold mb-2">The last {MAP_POINTS} transactions, by merchant location</h2>
          <svg viewBox={`0 0 ${mapW} ${mapH}`} className="w-full h-auto" role="img" aria-label="Merchant locations">
            <rect width={mapW} height={mapH} fill="var(--surface)" />
            {shown.map((e) =>
              e.decision === "approve" ? (
                <circle key={e.txn_id} cx={px(e.lon)} cy={py(e.lat)} r={1.8} fill="var(--cat-1)" opacity={0.45} />
              ) : e.decision === "review" ? (
                <path key={e.txn_id} d={`M${px(e.lon)},${py(e.lat) - 5}l4.5,8h-9z`} fill="var(--warning)" />
              ) : (
                <path
                  key={e.txn_id}
                  d={`M${px(e.lon) - 4},${py(e.lat) - 4}l8,8M${px(e.lon) + 4},${py(e.lat) - 4}l-8,8`}
                  stroke="var(--critical)"
                  strokeWidth={2.2}
                />
              ),
            )}
          </svg>
          <p className="text-xs text-ink2 mt-1">● approved · ▲ review · ✕ decline. Locations are Sparkov&apos;s generated merchant coordinates.</p>
        </section>

        <section className="border border-hairline bg-raised rounded-md p-3" aria-label="Threshold">
          <h2 className="text-sm font-semibold">Move the threshold</h2>
          {slider && recorded && threshold !== null ? (
            <>
              <input
                type="range"
                min={0}
                max={slider.points.length - 1}
                value={Math.max(0, slider.points.findIndex((p) => p >= threshold))}
                onChange={(e) => setThreshold(slider.points[Number(e.target.value)] ?? threshold)}
                className="w-full mt-3"
                aria-label="Decline threshold"
                data-testid="threshold"
              />
              <dl className="grid grid-cols-2 gap-2 mt-3 text-sm">
                <dt className="text-ink2">Threshold</dt>
                <dd className="num">{threshold.toFixed(4)}</dd>
                <dt className="text-ink2">Declined, test months</dt>
                <dd className="num">{formatValue(slider.current.flagged, "int")}</dd>
                <dt className="text-ink2">Precision</dt>
                <dd className="num">{formatValue(slider.current.precision, "pct1")}</dd>
                <dt className="text-ink2">Recall</dt>
                <dd className="num">{formatValue(slider.current.recall, "pct1")}</dd>
                <dt className="text-ink2">Expected cost</dt>
                <dd className="num">{formatValue(slider.current.cost, "usd0")}</dd>
                <dt className="text-ink2">Cost minimum on this histogram</dt>
                <dd className="num">
                  {formatValue(slider.best.cost, "usd0")} at {slider.best.t.toFixed(4)}
                </dd>
              </dl>
              <button type="button" className="mt-3 text-xs underline text-ink2" onClick={() => setThreshold(recorded.operating_point)}>
                Back to the operating point ({recorded.operating_point.toFixed(4)}), chosen on validation months
              </button>
              <p className="text-xs text-ink2 mt-2">
                Recomputed in your browser from the test months&apos; score histogram. The histogram is binned, so the
                minimum here is approximate; the operating point itself was chosen on validation data and never moved by
                this slider.
              </p>
            </>
          ) : (
            <div className="skeleton h-40 rounded" />
          )}
        </section>
      </div>
    </div>
  );
}
