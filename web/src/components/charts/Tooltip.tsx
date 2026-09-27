"use client";

export interface Tip {
  x: number;
  y: number;
  lines: string[];
}

export function Tooltip({ tip, width }: { tip: Tip | null; width: number }) {
  if (!tip) return null;
  const left = Math.min(Math.max(tip.x + 12, 0), width - 200);
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 rounded border border-hairline bg-surface px-2 py-1 text-xs text-ink shadow-lg"
      style={{ left, top: Math.max(tip.y - 10, 0), maxWidth: 220 }}
    >
      {tip.lines.map((line, i) => (
        <div key={i} className={i === 0 ? "font-semibold" : "num text-left"}>
          {line}
        </div>
      ))}
    </div>
  );
}
