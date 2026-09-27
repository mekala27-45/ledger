import type { NextConfig } from "next";

// Static export for GitHub Pages. The site lives under /ledger on the Pages domain;
// NEXT_PUBLIC_BASE_PATH is empty for local runs.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const config: NextConfig = {
  output: "export",
  basePath,
  assetPrefix: basePath || undefined,
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
