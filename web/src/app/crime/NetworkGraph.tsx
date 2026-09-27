"use client";

import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { useEffect, useMemo, useState } from "react";

import { useWidth } from "@/components/charts/useWidth";
import { formatValue } from "@/lib/format";

interface RawNode {
  id: string;
  community: number;
  alerted: string;
  injected: string;
  ring: number | null;
  outside: boolean;
}
interface RawLink {
  source: string;
  target: string;
  amount: number;
  transfers: number;
}
interface Net {
  nodes: RawNode[];
  links: RawLink[];
  communities: number[];
}
type Node = RawNode & SimulationNodeDatum;
type Link = SimulationLinkDatum<Node> & { amount: number; transfers: number };

// Three categorical slots, the validated maximum for a scatter; every other community is grey.
const SLOTS = ["var(--cat-1)", "var(--cat-2)", "var(--cat-3)"];

export function NetworkGraph({ base }: { base: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [net, setNet] = useState<Net | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const height = Math.min(620, Math.max(420, width * 0.7));

  useEffect(() => {
    fetch(`${base}/data/f05/network.json`)
      .then((r) => r.json() as Promise<Net>)
      .then(setNet)
      .catch(() => setNet(null));
  }, [base]);

  useEffect(() => {
    if (!net) return;
    const ns: Node[] = net.nodes.map((n) => ({ ...n }));
    const ls: Link[] = net.links.map((l) => ({ ...l }));
    const sim = forceSimulation<Node>(ns)
      .force("link", forceLink<Node, Link>(ls).id((d) => d.id).distance((l) => ((l.source as Node).outside || (l.target as Node).outside ? 14 : 26)).strength(0.9))
      .force("charge", forceManyBody().strength(-26))
      .force("collide", forceCollide(5))
      .force("x", forceX(width / 2).strength(0.04))
      .force("y", forceY(height / 2).strength(0.06))
      .force("center", forceCenter(width / 2, height / 2))
      .stop();
    // Settle off screen so the layout is steady and respects reduced motion.
    for (let i = 0; i < 320; i += 1) sim.tick();
    setNodes([...ns]);
    setLinks([...ls]);
  }, [net, width, height]);

  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const color = (n: Node) => (n.outside ? "var(--surface)" : n.community < SLOTS.length ? SLOTS[n.community] : "var(--control)");
  const chosen = selected ? byId.get(selected) : undefined;
  const chosenLinks = links.filter((l) => (l.source as Node).id === selected || (l.target as Node).id === selected);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      <div ref={ref} className="lg:col-span-3 relative">
        {nodes.length ? (
          <svg width={width} height={height} role="img" aria-label="Transfer network around alerted accounts" data-testid="network">
            {links.map((l, i) => {
              const s = l.source as Node;
              const t = l.target as Node;
              return (
                <line
                  key={i}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke="var(--hairline)"
                  strokeWidth={Math.min(3, 0.6 + Math.log10(1 + l.amount) / 2.5)}
                  opacity={selected && s.id !== selected && t.id !== selected ? 0.25 : 0.9}
                />
              );
            })}
            {nodes.map((n) => (
              <g
                key={n.id}
                transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                onClick={() => setSelected(n.id === selected ? null : n.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") setSelected(n.id === selected ? null : n.id);
                }}
                tabIndex={n.outside ? -1 : 0}
                role="button"
                aria-label={`${n.outside ? "Outside party" : "Account"} ${n.id}${n.alerted ? `, alerted: ${n.alerted}` : ""}`}
                className="cursor-pointer"
              >
                {n.ring !== null && n.alerted.includes("round_tripping") ? (
                  <circle r={9} fill="none" stroke="var(--critical)" strokeWidth={2} strokeDasharray="3 2" />
                ) : null}
                <circle
                  r={n.outside ? 2.5 : n.alerted ? 5.5 : 4}
                  fill={color(n)}
                  stroke={n.outside ? "var(--ink2)" : n.alerted ? "var(--ink)" : "var(--surface)"}
                  strokeWidth={n.alerted ? 1.8 : 0.8}
                />
              </g>
            ))}
          </svg>
        ) : (
          <div className="skeleton rounded" style={{ height }} />
        )}
        <ul className="flex flex-wrap gap-4 text-xs text-ink2 mt-2" aria-label="Legend">
          <li className="flex items-center gap-1">
            <svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="var(--cat-1)" stroke="var(--ink)" strokeWidth="1.8" /></svg>
            Alerted account (outlined)
          </li>
          <li className="flex items-center gap-1">
            <svg width="20" height="20" aria-hidden="true"><circle cx="10" cy="10" r="8" fill="none" stroke="var(--critical)" strokeWidth="2" strokeDasharray="3 2" /></svg>
            Planted ring member the round tripping rule found
          </li>
          <li className="flex items-center gap-1">
            <svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="2.5" fill="var(--surface)" stroke="var(--ink2)" /></svg>
            Outside party
          </li>
          <li>Colour: the three most suspicious communities; grey, every other</li>
        </ul>
      </div>
      <aside className="border border-hairline bg-raised rounded-md p-3 text-sm" aria-live="polite" data-testid="node-panel">
        {chosen ? (
          <>
            <div className="font-mono text-xs">{chosen.id}</div>
            <div className="text-xs text-ink2 mb-2">
              {chosen.outside ? "Outside party" : `Community ${chosen.community + 1} of those shown`}
              {chosen.alerted ? ` · alerted by ${chosen.alerted.replace(/_/g, " ")}` : ""}
              {chosen.injected ? ` · planted: ${chosen.injected.replace(/_/g, " ")}` : ""}
            </div>
            <table className="data-table w-full">
              <thead>
                <tr>
                  <th>With</th>
                  <th className="num">Money</th>
                  <th className="num">Transfers</th>
                </tr>
              </thead>
              <tbody>
                {chosenLinks.map((l, i) => {
                  const other = (l.source as Node).id === chosen.id ? (l.target as Node) : (l.source as Node);
                  return (
                    <tr key={i}>
                      <td className="font-mono text-[11px]">{other.id}</td>
                      <td className="num">{formatValue(l.amount, "usd0")}</td>
                      <td className="num">{l.transfers}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        ) : (
          <p className="text-ink2">Select an account to list the money that moved between it and its neighbours.</p>
        )}
      </aside>
    </div>
  );
}
