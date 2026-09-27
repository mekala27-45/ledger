// The scorecard's arithmetic in the browser, a line for line port of packages/scorecard so
// the studio and the API return the same score, probability, decision and reasons.

export interface ScoreBin {
  label: string;
  lower: number | null;
  upper: number | null;
  categories: string[];
  missing: boolean;
  goods: number;
  bads: number;
  woe: number;
  points: number;
}

export interface Characteristic {
  name: string;
  kind: "numeric" | "categorical";
  direction: number;
  coefficient: number;
  bins: ScoreBin[];
}

export interface Card {
  target: string;
  intercept: number;
  scaling: { base_score: number; base_odds: number; pdo: number; factor: number; offset: number };
  cutoff: number;
  candidates: string[];
  iv: Record<string, number>;
  dropped: Record<string, string>;
  characteristics: Characteristic[];
}

export interface FineBin {
  lower: number | null;
  upper: number | null;
  missing: boolean;
  goods: number;
  bads: number;
}

const SMOOTH = 0.5;

/** Half an observation added to both counts when a bin has no goods or no bads. */
export function smoothed(goods: number, bads: number): [number, number] {
  return goods === 0 || bads === 0 ? [goods + SMOOTH, bads + SMOOTH] : [goods, bads];
}

export function woeOf(goods: number, bads: number, totalGoods: number, totalBads: number): number {
  const [g, b] = smoothed(goods, bads);
  return Math.log(g / totalGoods / (b / totalBads));
}

export function contains(bin: ScoreBin, value: string | number | null): boolean {
  if (bin.missing) return value === null || value === "" || (typeof value === "number" && Number.isNaN(value));
  if (bin.categories.length) return bin.categories.includes(String(value));
  if (value === null || value === "") return false;
  const v = Number(value);
  if (Number.isNaN(v)) return false;
  return (bin.lower === null || v > bin.lower) && (bin.upper === null || v <= bin.upper);
}

/** The bin a value falls in; an unseen category takes the riskiest bin, as in the pipeline. */
export function indexOf(c: Characteristic, value: string | number | null): number {
  const i = c.bins.findIndex((b) => contains(b, value));
  if (i >= 0) return i;
  let worst = 0;
  c.bins.forEach((b, j) => {
    if (b.woe < (c.bins[worst]?.woe ?? Infinity)) worst = j;
  });
  return worst;
}

export function probabilityOfBad(card: Card, score: number): number {
  const logOddsGood = (score - card.scaling.offset) / card.scaling.factor;
  return 1 / (1 + Math.exp(logOddsGood));
}

/** Points for a bin at a characteristic's fitted coefficient. */
export function pointsFor(card: Card, coefficient: number, woe: number): number {
  const n = card.characteristics.length;
  return -(coefficient * woe + card.intercept / n) * card.scaling.factor + card.scaling.offset / n;
}

export interface Scored {
  score: number;
  probability: number;
  decision: "approve" | "decline";
  points: Record<string, number>;
  reasons: string[];
}

/** Reg B reasons: the characteristics furthest below their best attainable points, at most four. */
export function scoreApplicant(
  card: Card,
  applicant: Record<string, string | number | null>,
  reasonText: Record<string, string>,
  top = 4,
): Scored {
  const points: Record<string, number> = {};
  let total = 0;
  const gaps: { name: string; gap: number }[] = [];
  for (const c of card.characteristics) {
    const got = c.bins[indexOf(c, applicant[c.name] ?? null)]?.points ?? 0;
    points[c.name] = got;
    total += got;
    const best = Math.max(...c.bins.map((b) => b.points));
    if (best - got > 1e-9) gaps.push({ name: c.name, gap: best - got });
  }
  const decision = total >= card.cutoff ? "approve" : "decline";
  const reasons =
    decision === "decline"
      ? gaps
          .sort((a, b) => b.gap - a.gap)
          .slice(0, top)
          .map((g) => {
            const text = reasonText[g.name];
            if (!text) throw new Error(`no plain language reason on file for ${g.name}`);
            return text;
          })
      : [];
  return { score: total, probability: probabilityOfBad(card, total), decision, points, reasons };
}

export interface CoarseBin {
  label: string;
  lower: number | null;
  upper: number | null;
  goods: number;
  bads: number;
  share: number;
  badRate: number;
  woe: number;
  iv: number;
  points: number;
}

function edgeText(x: number): string {
  return Math.abs(x) >= 1000 ? x.toLocaleString("en-US", { maximumFractionDigits: 0 }) : String(Number(x.toPrecision(4)));
}

/** Merge fine bins between the chosen edges and recompute everything that depends on them. */
export function coarsen(card: Card, coefficient: number, fine: FineBin[], edges: number[]): CoarseBin[] {
  const ordered = fine.filter((b) => !b.missing);
  const missing = fine.filter((b) => b.missing);
  const cuts = [...new Set(edges)].filter((e) => e >= 0 && e < ordered.length - 1).sort((a, b) => a - b);
  const groups: FineBin[][] = [];
  let start = 0;
  for (const cut of [...cuts, ordered.length - 1]) {
    groups.push(ordered.slice(start, cut + 1));
    start = cut + 1;
  }
  if (missing.length) groups.push(missing);
  const totalGoods = fine.reduce((s, b) => s + b.goods, 0);
  const totalBads = fine.reduce((s, b) => s + b.bads, 0);
  return groups.map((g) => {
    const goods = g.reduce((s, b) => s + b.goods, 0);
    const bads = g.reduce((s, b) => s + b.bads, 0);
    const woe = woeOf(goods, bads, totalGoods, totalBads);
    const [sg, sb] = smoothed(goods, bads);
    const lower = g[0]?.lower ?? null;
    const upper = g[g.length - 1]?.upper ?? null;
    const isMissing = g.every((b) => b.missing);
    return {
      label: isMissing ? "missing" : `(${lower === null ? "-inf" : edgeText(lower)}, ${upper === null ? "+inf" : edgeText(upper)}]`,
      lower,
      upper,
      goods,
      bads,
      share: (goods + bads) / (totalGoods + totalBads),
      badRate: goods + bads ? bads / (goods + bads) : NaN,
      woe,
      iv: (sg / totalGoods - sb / totalBads) * woe,
      points: pointsFor(card, coefficient, woe),
    };
  });
}

/** Monotone means the WoE never changes direction across the ordered, non missing bins. */
export function monotone(bins: CoarseBin[]): { ok: boolean; direction: "rises" | "falls" | "flat"; breaks: number[] } {
  const woes = bins.filter((b) => b.label !== "missing").map((b) => b.woe);
  const rising = woes.every((w, i) => i === 0 || (woes[i - 1] ?? w) <= w + 1e-12);
  const falling = woes.every((w, i) => i === 0 || (woes[i - 1] ?? w) >= w - 1e-12);
  if (rising && falling) return { ok: true, direction: "flat", breaks: [] };
  if (rising) return { ok: true, direction: "rises", breaks: [] };
  if (falling) return { ok: true, direction: "falls", breaks: [] };
  // Name the bins where the direction reverses against the overall trend.
  const trend = (woes[woes.length - 1] ?? 0) >= (woes[0] ?? 0) ? 1 : -1;
  const breaks = woes.flatMap((w, i) => (i > 0 && (w - (woes[i - 1] ?? w)) * trend < -1e-12 ? [i] : []));
  return { ok: false, direction: trend > 0 ? "rises" : "falls", breaks };
}

/** The fine bin boundaries the pipeline's coarse bins sit on. */
export function fittedEdges(c: Characteristic, fine: FineBin[]): number[] {
  const ordered = fine.filter((b) => !b.missing);
  const uppers = c.bins.filter((b) => !b.missing && b.upper !== null).map((b) => b.upper as number);
  return uppers
    .map((u) => ordered.findIndex((f) => f.upper !== null && Math.abs(f.upper - u) <= 1e-9 * Math.max(1, Math.abs(u))))
    .filter((i) => i >= 0 && i < ordered.length - 1);
}
