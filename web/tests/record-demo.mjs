// Records the desk's recorded replay as PNG frames for scripts/build_demo_gif.py.
// Usage: node tests/record-demo.mjs <url> <out-dir> <frames> <interval-ms>
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const [, , url, out, framesArg = "48", intervalArg = "250"] = process.argv;
const frames = Number(framesArg);
const interval = Number(intervalArg);
mkdirSync(out, { recursive: true });
const executablePath = process.env.PLAYWRIGHT_CHROMIUM || undefined;
const browser = await chromium.launch(executablePath ? { executablePath } : {});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
await page.goto(url, { waitUntil: "networkidle" });
const desk = page.locator('section[aria-label="The desk"]');
await desk.scrollIntoViewIfNeeded();
const faster = page.getByRole("button", { name: /4 h per second/ });
if (await faster.count()) await faster.first().click();
await page.waitForTimeout(1500);
for (let i = 0; i < frames; i++) {
  await desk.screenshot({ path: join(out, `frame-${String(i).padStart(3, "0")}.png`) });
  await page.waitForTimeout(interval);
}
await browser.close();
