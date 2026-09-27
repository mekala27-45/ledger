// Build time readers for the committed bundle in public/data. Pages that only show
// aggregates render them into static HTML; interactive pages fetch at run time.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { type Manifest, ManifestView } from "./manifest";

const DATA = join(process.cwd(), "public", "data");

export function readJson<T>(relative: string): T {
  return JSON.parse(readFileSync(join(DATA, relative), "utf8")) as T;
}

export function readText(relative: string): string {
  return readFileSync(join(DATA, relative), "utf8");
}

let cached: ManifestView | null = null;
export function manifest(): ManifestView {
  if (!cached) cached = new ManifestView(readJson<Manifest>("manifest.json"));
  return cached;
}

export interface Statements {
  demonstration: string;
  not_a_decision: string;
}

/** Both statements, written once in packages/core and exported with the bundle. */
export function statements(): Statements {
  return readJson<Statements>("statements.json");
}
