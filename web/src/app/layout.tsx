import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";

import { Shell } from "@/components/Shell";

import "./globals.css";

// Self hosted at build time from @fontsource. Manrope carries tabular figures (tnum),
// checked in the build; the mono is for the transaction feed, identifiers and code.
const manrope = localFont({
  variable: "--font-manrope",
  display: "swap",
  src: [
    { path: "../../node_modules/@fontsource/manrope/files/manrope-latin-400-normal.woff2", weight: "400" },
    { path: "../../node_modules/@fontsource/manrope/files/manrope-latin-600-normal.woff2", weight: "600" },
    { path: "../../node_modules/@fontsource/manrope/files/manrope-latin-700-normal.woff2", weight: "700" },
  ],
});
const instrument = localFont({
  variable: "--font-instrument",
  display: "swap",
  src: [{ path: "../../node_modules/@fontsource/instrument-serif/files/instrument-serif-latin-400-normal.woff2", weight: "400" }],
});
const martian = localFont({
  variable: "--font-martian",
  display: "swap",
  src: [{ path: "../../node_modules/@fontsource/martian-mono/files/martian-mono-latin-400-normal.woff2", weight: "400" }],
});

export const metadata: Metadata = {
  title: { default: "ledger: a retail bank's analytics function", template: "%s | ledger" },
  description:
    "The analytics function of a fictional retail bank: a live fraud desk, a scorecard studio, model risk management and a general ledger that reconciles to the cent.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0E1117" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${manrope.variable} ${instrument.variable} ${martian.variable}`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
