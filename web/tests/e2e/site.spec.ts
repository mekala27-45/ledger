import { expect, test } from "@playwright/test";

import { ROUTES } from "./routes";

const DEMONSTRATION = /Harborline Bank is fictional/;
const NOT_A_DECISION = /Nothing here is a credit decision/;

for (const route of ROUTES) {
  test(`${route} carries both statements, a heading and no console errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto(route);
    await expect(page.locator("h1").first()).toBeVisible();
    const footer = page.getByTestId("statements");
    await expect(footer.locator('[data-statement="demonstration"]')).toHaveText(DEMONSTRATION);
    await expect(footer.locator('[data-statement="not-a-decision"]')).toHaveText(NOT_A_DECISION);
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
  });
}

test("the navigation links only to pages that exist", async ({ page, request }) => {
  await page.goto("/");
  const hrefs = await page.locator('nav[aria-label="Functions"] a').evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  expect(hrefs.length).toBeGreaterThan(5);
  for (const href of hrefs) {
    const r = await request.get(href ?? "/");
    expect(r.status(), href ?? "").toBe(200);
  }
});

test("every chart has a table toggle that shows its data", async ({ page }) => {
  for (const route of ["/", "/desk/", "/lending/", "/models/", "/controls/"]) {
    await page.goto(route);
    const toggles = page.getByTestId("table-toggle");
    const n = await toggles.count();
    expect(n, route).toBeGreaterThan(0);
    await toggles.first().click();
    await expect(page.getByRole("region", { name: "Chart data" }).first()).toBeVisible();
  }
});

test("the desk plays the recorded replay and says so when there is no API", async ({ page }) => {
  await page.goto("/desk/");
  await expect(page.getByTestId("desk-mode")).toContainText("Recorded replay");
  await page.getByRole("button", { name: /16 h per second/ }).click();
  await expect(page.getByTestId("feed").locator("tbody tr").first()).toBeVisible();
  await expect(page.getByTestId("late-labels")).toContainText("chargeback window");
});

test("the threshold slider recomputes precision in the browser", async ({ page }) => {
  await page.goto("/desk/");
  const slider = page.getByTestId("threshold");
  await expect(slider).toBeVisible();
  const precision = page.locator("dt:text('Precision') + dd");
  const before = await precision.textContent();
  await slider.focus();
  for (let i = 0; i < 15; i += 1) await page.keyboard.press("ArrowRight");
  await expect(precision).not.toHaveText(before ?? "");
});

test("removing a bin edge in the studio updates the bins and the information value", async ({ page }) => {
  await page.goto("/studio/");
  const handles = page.getByTestId("edge-handle");
  const edges = await handles.count();
  expect(edges).toBeGreaterThan(1);
  const iv = page.getByTestId("iv");
  const before = await iv.textContent();
  const rows = page.getByTestId("coarse-table").locator("tbody tr");
  await expect(rows).toHaveCount(edges + 1);
  await handles.first().focus();
  await page.keyboard.press("Delete");
  await expect(rows).toHaveCount(edges);
  await expect(iv).not.toHaveText(before ?? "");
  await page.getByRole("button", { name: "Reset to the fitted bins" }).click();
  await expect(rows).toHaveCount(edges + 1);
  await expect(iv).toHaveText(before ?? "");
});

test("the studio scores an applicant and gives reasons for a decline", async ({ page }) => {
  await page.goto("/studio/");
  await page.getByRole("button", { name: "Score", exact: true }).click();
  await expect(page.getByTestId("score")).toHaveText(/^\d{3}\.\d$/);
  await expect(page.getByTestId("decision")).toHaveText(/approve|decline/);
  // A thin file with heavy utilisation and a large request is declined, with reasons.
  const form = page.getByTestId("applicant-form");
  await form.locator('input[name="revolving_utilization"]').fill("0.95");
  await form.locator('input[name="dti"]').fill("0.45");
  await form.locator('input[name="bureau_score"]').fill("600");
  await form.locator('input[name="employment_months"]').fill("3");
  await page.getByRole("button", { name: "Score", exact: true }).click();
  await expect(page.getByTestId("decision")).toHaveText(/decline/);
  await expect(page.getByTestId("reasons").locator("li")).toHaveCount(4);
  await expect(page.getByTestId("applicant-result")).toContainText("Scored in your browser");
});

test("DuckDB runs SQL over the warehouse in the browser", async ({ page }) => {
  await page.goto("/explore/");
  await expect(page.getByTestId("explore-status")).toContainText("rows in", { timeout: 40_000 });
  await page.getByTestId("sql").fill("select count(*) as n from gl_account_month where reported_balance <> balance_from_postings");
  await page.getByTestId("run").click();
  await expect(page.getByTestId("result").locator("tbody td").first()).toHaveText("6");
});

test("a validation report and the board pack render", async ({ page }) => {
  await page.goto("/models/fraud_card/");
  await expect(page.locator("article h2").first()).toBeVisible();
  await page.goto("/report/");
  await expect(page.getByTestId("board-pack")).toContainText("board pack");
  await expect(page.getByTestId("board-pack")).toHaveAttribute("data-theme", "light");
});

test("the theme toggle switches between the dark and light themes", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: /theme/i }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("the fair lending map toggles between unadjusted and adjusted rates", async ({ page }) => {
  await page.goto("/fair-lending/");
  const map = page.getByRole("img", { name: /by county/ });
  await expect(map.locator("path").first()).toBeVisible();
  const fills = async () => map.locator("path").evaluateAll((ps) => ps.map((p) => p.getAttribute("fill")).join(","));
  const before = await fills();
  await page.getByTestId("measure-adjusted_rate").click();
  await expect.poll(fills).not.toBe(before);
  await expect(map.locator("path")).toHaveCount(21);
});

test("the investigator graph lists an account's transfers on click", async ({ page }) => {
  await page.goto("/crime/");
  const graph = page.getByTestId("network");
  await expect(graph).toBeVisible();
  await graph.getByRole("button", { name: /alerted/ }).first().click();
  await expect(page.getByTestId("node-panel").locator("tbody tr").first()).toBeVisible();
  await expect(page.getByTestId("case-queue").locator("tbody tr").first()).toBeVisible();
});
