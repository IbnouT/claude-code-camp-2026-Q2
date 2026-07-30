import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function mockCapabilities(page: Page) {
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
            state: "unavailable",
            detail: "Failure injected by the end-to-end gate",
          },
          {
            id: "agent",
            label: "Agent events",
            state: "disabled",
            detail: "Not configured",
          },
          {
            id: "benchmark",
            label: "Benchmark evidence",
            state: "ready",
            detail: "Configured source is readable",
          },
          {
            id: "knowledge",
            label: "Knowledge store",
            state: "disabled",
            detail: "Not configured",
          },
        ],
        features: [
          "live",
          "replay",
          "time-travel",
          "diagnostics",
          "compare",
          "query",
        ],
      }),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockCapabilities(page);
  await page.goto("/");
});

test("renders the source failure honestly and passes accessibility", async ({ page }) => {
  await expect(page.getByText("Failure injected by the end-to-end gate")).toBeVisible();
  await expect(page.getByText("Instrumentation issue")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("persists light theme without losing the workspace", async ({ page }) => {
  await page.getByRole("button", { name: "Use light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.waitForTimeout(250);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("heading", { name: "Living world" })).toBeVisible();
});

test("provides complete narrow navigation without horizontal root clipping", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "narrow", "narrow project only");
  const size = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(size.scroll).toBeLessThanOrEqual(size.client);
  await page.getByRole("button", { name: "Experiments" }).click();
  await expect(page.getByText(/Design controlled comparisons/)).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Session" })).toHaveCount(0);
  await page.getByRole("button", { name: "Search experiments" }).click();
  await expect(page.getByRole("dialog", { name: "Ask or search evidence" })).toBeVisible();
});

test("keeps agent control scoped and non-mutating in B1", async ({ page }) => {
  await page.getByRole("button", { name: /Direct the agent/ }).click();
  const dialog = page.getByRole("dialog", { name: "Direct the selected agent" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("poucet", { exact: true })).toBeVisible();
  await expect(dialog.getByText("live-poucet", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Preview only/ })).toBeDisabled();
});

test("remains operable with forced colors and reduced motion", async ({ page }) => {
  await page.emulateMedia({
    forcedColors: "active",
    reducedMotion: "reduce",
  });
  await page.reload();
  await expect(page.getByRole("navigation", { name: "Observatory spaces" })).toBeVisible();
  await page.getByRole("button", { name: "Ask about this run" }).click();
  const duration = await page.getByRole("dialog").evaluate(
    (element) => getComputedStyle(element).animationDuration,
  );
  expect(Number.parseFloat(duration)).toBeLessThanOrEqual(0.01);
});

test("restores focus after the scoped investigation dialog closes", async ({ page }) => {
  const trigger = page.getByRole("button", { name: "Ask about this run" });
  await trigger.click();
  await expect(page.getByRole("textbox", { name: "Question or evidence query" }))
    .toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("keeps the complete shell reachable at a 200 percent layout equivalent", async ({
  page,
}) => {
  await page.setViewportSize({ width: 720, height: 450 });
  await expect(page.getByRole("navigation", { name: "Observatory spaces" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Player" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Session" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask about this run" })).toBeVisible();
  const scroll = await page.evaluate(() => ({
    clientHeight: document.documentElement.clientHeight,
    scrollHeight: document.documentElement.scrollHeight,
    overflowY: getComputedStyle(document.body).overflowY,
  }));
  expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);
  expect(scroll.overflowY).not.toBe("hidden");
});
