// The manifest as the site reads it: every number on every page comes from here or from a
// results file the same pipeline wrote.
import { formatValue, type Scalar } from "./format";

export interface Provenance {
  backend: string;
  population: string;
  as_of: string;
  source: string;
  seed: number | null;
}
export interface ValueEntry {
  value: Scalar;
  fmt: string;
  provenance: Provenance;
}
export interface TableEntry {
  columns: string[];
  formats: string[];
  rows: Scalar[][];
  provenance: Provenance;
}
export interface FigureEntry {
  title: string;
  callout: string;
  data: string | null;
  provenance: Provenance;
}
export interface Manifest {
  as_of: string;
  seed: number;
  values: Record<string, ValueEntry>;
  tables: Record<string, TableEntry>;
  figures: Record<string, FigureEntry>;
}

export class ManifestView {
  constructor(private readonly m: Manifest) {}

  has(key: string): boolean {
    return key in this.m.values || key in this.m.tables || key in this.m.figures;
  }
  /** Whether any entry starts with the prefix, such as a function code, "f03.". */
  hasPrefix(prefix: string): boolean {
    return [this.m.values, this.m.tables, this.m.figures].some((section) => Object.keys(section).some((k) => k.startsWith(prefix)));
  }
  raw(key: string): Scalar {
    const entry = this.m.values[key];
    if (!entry) throw new Error(`manifest has no value ${key}`);
    return entry.value;
  }
  num(key: string): number {
    const v = this.raw(key);
    return typeof v === "number" ? v : Number(v);
  }
  v(key: string): string {
    const entry = this.m.values[key];
    if (!entry) throw new Error(`manifest has no value ${key}`);
    return formatValue(entry.value, entry.fmt);
  }
  table(key: string): TableEntry {
    const entry = this.m.tables[key];
    if (!entry) throw new Error(`manifest has no table ${key}`);
    return entry;
  }
  figure(key: string): FigureEntry {
    const entry = this.m.figures[key];
    if (!entry) throw new Error(`manifest has no figure ${key}`);
    return entry;
  }
  label(key: string): string {
    const entry = this.m.figures[key] ?? this.m.tables[key] ?? this.m.values[key];
    if (!entry) throw new Error(`manifest has no entry ${key}`);
    const p = entry.provenance;
    const seed = p.seed !== null && p.seed !== undefined ? `, seed ${p.seed}` : "";
    return `Source: ${p.backend}, ${p.population}${seed}, as of ${p.as_of}.`;
  }
  get asOf(): string {
    return this.m.as_of;
  }
}
