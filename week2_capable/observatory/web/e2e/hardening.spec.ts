import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function mockSources(
  page: Page,
  features = [
    "live",
    "replay",
    "time-travel",
    "diagnostics",
    "compare",
    "incident-capsules",
  ],
) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path === "/api/capabilities"
      ? {
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
            state: "disabled",
            detail: "Not configured",
          },
          {
            id: "knowledge",
            label: "Knowledge store",
            state: "disabled",
            detail: "Not configured",
          },
        ],
        features,
      }
      : path === "/api/sessions"
        ? { sessions: [] }
        : path === "/api/runs"
          ? { runs: [] }
          : path === "/api/comparisons"
            ? { comparisons: [] }
            : { error: "unavailable" };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockSources(page);
  await page.goto("/");
});

test("keeps the source failure visible and the shell accessible", async ({
  page,
}) => {
  await page.getByText("sources", { exact: true }).click();
  await expect(page.getByText("Failure injected by the end-to-end gate"))
    .toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("opens the capsule workflow without any evidence source", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Capsules" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("Read-only evidence")).toBeVisible();
  await expect(page.getByText("Open capsule")).toBeVisible();
});

test("fits the complete workspace inside a narrow viewport", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "narrow", "narrow project only");
  const width = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(width.scroll).toBeLessThanOrEqual(width.client);
  await page.getByRole("button", { name: "Capsules" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("honors capability policy instead of exposing disabled modes", async ({
  page,
}) => {
  await page.unroute("**/api/**");
  await mockSources(page, ["live", "incident-capsules"]);
  await page.reload();
  await expect(page.getByRole("button", { name: "Live", exact: true }))
    .toBeVisible();
  await expect(page.getByRole("button", { name: "Investigate" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Compare" })).toHaveCount(0);
});

test("remains operable with forced colors and reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({
    forcedColors: "active",
    reducedMotion: "reduce",
  });
  await page.reload();
  await expect(page.getByRole("navigation", { name: "Observatory modes" }))
    .toBeVisible();
  await page.getByRole("button", { name: "Capsules" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const duration = await page.locator(".incident-workflow").evaluate(
    (element) => getComputedStyle(element).animationDuration,
  );
  expect(Number.parseFloat(duration)).toBeLessThanOrEqual(0.01);
});
