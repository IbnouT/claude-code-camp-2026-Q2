import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mockRuntime } from "./runtimeFixture";

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
  await mockRuntime(page);
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
  await expect(page.getByRole("heading", { name: /Living world/ })).toBeVisible();
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

test("keeps agent control scoped to the selected live session", async ({ page }) => {
  await page.getByRole("button", { name: /Direct the agent/ }).click();
  const dialog = page.getByRole("dialog", { name: "Direct the selected agent" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("alpha", { exact: true })).toBeVisible();
  await expect(dialog.getByText("session-alpha", { exact: true })).toBeVisible();
  await dialog.getByRole("textbox", { name: "Operator guidance" })
    .fill("Inspect the west exit before choosing another route.");
  await dialog.getByRole("button", { name: "Confirm guide" }).click();
  await expect(dialog.getByText("guide accepted")).toBeVisible();
  await expect(dialog.getByText(/next iteration boundary/)).toBeVisible();
});

test("reconstructs a selected prefix and returns to the live combat state", async ({
  page,
}) => {
  await expect(page.getByRole("heading", { name: "Living world · combat" }))
    .toBeVisible();
  await page.getByRole("slider", { name: "Selected sequence" }).fill("2");
  await expect(page.getByRole("heading", { name: "Living world" })).toBeVisible();
  await expect(page.getByText("The Temple Of Midgaard", { exact: true }).first())
    .toBeVisible();
  await expect(page.getByText("Viewing history", { exact: true }).first())
    .toBeVisible();

  await page.getByRole("button", { name: "Return to live" }).click();

  await expect(page.getByRole("heading", { name: "Living world · combat" }))
    .toBeVisible();
  await expect(page.getByText("Hidden Courtyard", { exact: true }).first())
    .toBeVisible();
});

test("switches players without retaining the prior session evidence", async ({
  page,
}) => {
  await page.getByRole("combobox", { name: "Player" }).selectOption("beta");
  await expect(page.getByRole("combobox", { name: "Session" }))
    .toHaveValue("session-beta");
  await expect(page.getByText("Beta Field", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("The Temple Of Midgaard", { exact: true }))
    .toHaveCount(0);
  await expect(page.getByRole("button", { name: "Control unavailable" }))
    .toBeDisabled();
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
