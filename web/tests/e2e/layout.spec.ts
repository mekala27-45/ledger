import { expect, test } from "@playwright/test";

import { ROUTES } from "./routes";

// At phone width no page may scroll sideways; wide tables and charts scroll inside themselves.
for (const route of ROUTES) {
  test(`${route} has no horizontal page scroll`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
