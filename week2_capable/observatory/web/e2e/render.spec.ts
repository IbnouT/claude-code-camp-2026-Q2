import { expect, test, type Page } from "@playwright/test";
import { mockRecorded } from "./recordedFixture";
import { mockRuntime } from "./runtimeFixture";

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

test("captures the B2 Live cockpit for rendered review", async ({ page }, testInfo) => {
  await renderFixture(page);
  await mockRuntime(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Living world · combat" }))
    .toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b2-live-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: /Direct the agent/ }).click();
  await expect(
    page.getByRole("dialog", { name: "Direct the selected agent" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b2-control-dark.png"),
    fullPage: false,
  });
  await page.getByRole("button", { name: "Close agent control" }).click();

  await page.getByRole("button", { name: "Use light theme" }).click();
  await page.waitForTimeout(250);
  await page.screenshot({
    path: testInfo.outputPath("b2-live-light.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Lantern" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b4-lantern-light.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Atlas" }).click();
  await expect(page.getByRole("img", { name: /Observer atlas overview/ }))
    .toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b4-atlas-light.png"),
    fullPage: true,
  });
});

test("captures the B3 Sessions investigation for rendered review", async ({
  page,
}, testInfo) => {
  await renderFixture(page);
  await mockRuntime(page);
  await mockRecorded(page);
  await page.goto("/?space=sessions");
  await expect(
    page.getByRole("heading", {
      name: "J2 Travel north and find the Massive Minotaur.",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b3-sessions-story-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /White Square, place 12/ }).click();
  await expect(page.getByText("Why this remains a candidate")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b4-session-candidates-dark.png"),
    fullPage: true,
  });

  await page.getByRole("tab", { name: "Cost", exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath("b3-sessions-cost-dark.png"),
    fullPage: true,
  });

  await page.getByRole("tab", { name: /Diagnostics/ }).click();
  await page.getByRole("button", { name: "Use light theme" }).click();
  await page.waitForTimeout(150);
  await page.screenshot({
    path: testInfo.outputPath("b3-sessions-diagnostics-light.png"),
    fullPage: true,
  });
});
