import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mockRuntime } from "./runtimeFixture";
import {
  mockCompletedExperiment,
  mockExperiment,
  mockExperimentExecution,
} from "./experimentFixture";

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
  await mockExperiment(page);
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

test("prefers a live player when recorded evidence loads first", async ({
  page,
}) => {
  await page.unroute("**/api/sessions");
  await mockRuntime(page, 250);
  await page.goto("/?space=live");
  await expect(page.getByRole("combobox", { name: "Player" }))
    .toHaveValue("alpha");
  await expect(page.getByRole("combobox", { name: "Session" }))
    .toHaveValue("session-alpha");
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
  await expect(page.getByRole("heading", { name: "Model-facing result rendering" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Session" })).toHaveCount(0);
  await expect(page.getByText(/Validation and explicit spend confirmation/)).toBeVisible();
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

test("forks one registered experiment value with visible provenance", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Experiments" }).click();
  await page.getByRole("button", { name: "Fork one variable" }).click();
  await page.getByLabel("Arm").selectOption("minimal");
  await page.getByLabel("Feature").selectOption("tools.profile");
  await page.getByLabel("New value").selectOption("direct-core");
  await page.getByRole("button", { name: "Create immutable fork" }).click();
  await expect(page.getByRole("status")).toContainText(
    "minimal:tools.profile",
  );
  await expect(page.getByRole("status")).toContainText(
    "j1-rendering-n10-definition",
  );
});

test("reveals spend confirmation only after deterministic validation", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Experiments" }).click();
  await page.getByRole("button", { name: "Run queue" }).click();
  const confirmation = page.getByLabel(/I confirm this exact definition/);
  await expect(confirmation).toBeDisabled();
  await page.getByRole("button", { name: "Validate effective definition" }).click();
  await expect(page.getByRole("status")).toContainText("Validation passed");
  await expect(confirmation).toBeEnabled();
  await confirmation.check();
  await page.getByRole("button", { name: "Start controlled run" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "execution is disabled by local policy",
  );
});

test("creates a small executable draft and validates registry-generated values", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Experiments" }).click();
  await page.getByRole("button", { name: "New", exact: true }).click();
  await expect(page.getByRole("heading", { name: /result rendering pilot/ }))
    .toBeVisible();
  await expect(page.getByLabel("Repetitions per arm")).toHaveValue("1");
  await expect(page.getByText("Maximum spend $1.80")).toBeVisible();
  await page.getByLabel("Arm to configure").selectOption("raw");
  await page.getByLabel("Gateway tool surface").selectOption("direct-core");

  const validationRequest = page.waitForRequest("**/api/experiments/validate");
  await page.getByRole("button", { name: "Run queue" }).click();
  await page.getByRole("button", { name: "Validate effective definition" }).click();
  const request = await validationRequest;
  const payload = request.postDataJSON() as {
    definition: {
      source: string;
      arms: { id: string; values: Record<string, unknown> }[];
    };
  };
  expect(payload.definition.source).toBe("executable_definition");
  expect(payload.definition.arms.find((arm) => arm.id === "raw")?.values["tools.profile"])
    .toBe("direct-core");
});

test("watches, stops, and resumes a confirmed job without changing sample identity", async ({
  page,
}) => {
  await mockExperimentExecution(page);
  await page.getByRole("button", { name: "Experiments" }).click();
  await page.getByRole("button", { name: "Run queue" }).click();
  await page.getByRole("button", { name: "Validate effective definition" }).click();
  await page.getByLabel(/I confirm this exact definition/).check();
  await page.getByRole("button", { name: "Start controlled run" }).click();
  await expect(page.getByRole("alert")).toContainText("Controlled run queued");
  await expect(page.getByRole("heading", { name: "raw-001-fixture" })).toBeVisible();

  await page.getByRole("button", { name: "Stop safely" }).click();
  await expect(page.getByRole("heading", { name: "Job stopped" })).toBeVisible();
  await expect(page.getByText("raw-001-fixture", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByRole("heading", { name: "raw-001-fixture" })).toBeVisible();

  await page.reload();
  const persistedJob = page.locator(".experiment-rail .experiment-card")
    .filter({ hasText: "result rendering pilot" });
  await expect(persistedJob).toBeVisible();
  await persistedJob.click();
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Results from this controlled definition" }))
    .toBeVisible();
  await expect(page.getByText("Incomplete arms remain visibly incomplete"))
    .toBeVisible();
});

test("keeps setup failures out of the verified outcome denominator", async ({
  page,
}) => {
  await mockCompletedExperiment(page);
  await page.getByRole("button", { name: "Experiments" }).click();
  const persisted = page.locator(".experiment-rail .experiment-card")
    .filter({ hasText: "Completed result rendering pilot" });
  await persisted.click();

  const arms = page.locator(".experiment-arm");
  await expect(arms.nth(0)).toContainText("1/1");
  await expect(arms.nth(1)).toContainText("0/1");
  await expect(arms.nth(2).locator(".arm-value").nth(0)).toContainText("—");
  await expect(arms.nth(2)).toContainText("1 / 0");
  await arms.nth(2).click();
  await expect(page.getByRole("heading", {
    name: "Every planned repetition remains visible",
  })).toBeVisible();
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

test("keeps spatial framing explainable and atlas truth quarantined", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Lantern" }).click();
  await expect(page.getByRole("button", { name: "Lantern" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Massive Minotaur", { exact: false }).first())
    .toBeVisible();
  await expect(page.getByText("Objective entity sighted", { exact: false }))
    .toBeVisible();

  await page.getByRole("button", { name: "Atlas" }).click();
  await expect(
    page.getByRole("img", { name: /Observer atlas overview, 33 zone clusters/ }),
  ).toBeVisible();
  await expect(page.getByText("1,878 rooms")).toBeVisible();
  await expect(page.getByText(/Observer truth is isolated/)).toBeVisible();
  await expect(page.locator(".world-atlas-canvas [data-room-id]")).toHaveCount(0);
  await expect.poll(async () => Number.parseFloat(
    await page.getByTestId("atlas-frame").innerText(),
  )).toBeLessThan(50);

  await page.getByText("Explore the atlas as a structured list").click();
  await page.getByRole("button", { name: /Zone 30/ }).click();
  await expect(
    page.getByRole("img", { name: /Observer atlas zone 30, 61 rooms/ }),
  ).toBeVisible();
  await expect(page.getByText(/not correlated to the selected journey/))
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
