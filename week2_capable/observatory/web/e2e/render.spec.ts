import { expect, test, type Page } from "@playwright/test";

async function renderFixture(page: Page) {
  await page.route("**/api/capabilities", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        sources: [
          {
            id: "gateway",
            label: "Gateway journal",
            state: "ready",
            detail: "Connected · 240 ms freshness",
          },
          {
            id: "agent",
            label: "Agent events",
            state: "ready",
            detail: "Selected live session is observable",
          },
          {
            id: "benchmark",
            label: "Benchmark evidence",
            state: "disabled",
            detail: "Not needed in Live",
          },
          {
            id: "knowledge",
            label: "Knowledge store",
            state: "ready",
            detail: "Player-owned store is readable",
          },
        ],
        features: [
          "live",
          "replay",
          "time-travel",
          "diagnostics",
          "query",
          "knowledge-overview",
        ],
      }),
    });
  });
}

test("captures the B1 shell for rendered review", async ({ page }, testInfo) => {
  await renderFixture(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Living world" })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b1-shell-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Use light theme" }).click();
  await page.waitForTimeout(250);
  await page.screenshot({
    path: testInfo.outputPath("b1-shell-light.png"),
    fullPage: true,
  });
});
