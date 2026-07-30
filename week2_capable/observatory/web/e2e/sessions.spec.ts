import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockRecorded } from "./recordedFixture";
import { mockRuntime } from "./runtimeFixture";

test.beforeEach(async ({ page }) => {
  await mockRuntime(page);
  await mockRecorded(page);
  await page.goto("/?space=sessions");
  await expect(
    page.getByRole("heading", {
      name: "J2 Travel north and find the Massive Minotaur.",
    }),
  ).toBeVisible();
});

test("diagnoses J2 from final claim to exact linked evidence", async ({ page }) => {
  await page.getByRole("tab", { name: /Diagnostics/ }).click();
  await expect(
    page.getByRole("heading", {
      name: "The run ended before the objective was verified",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Verified objective not satisfied" })
    .click();
  await expect(page.getByText("benchmark record 1")).toBeVisible();
  await expect(page).toHaveURL(/record=benchmark%3Aoutcome/);

  await page.getByRole("button", { name: "Ask why" }).click();
  await page.getByRole("textbox", { name: "Question or evidence query" })
    .fill("Why did the agent stop?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("The linked objective predicate remained false."))
    .toBeVisible();
  await expect(page.getByText("$0.0000 model spend")).toBeVisible();
});

test("replays by retained moment and never uses future stop evidence", async ({
  page,
}) => {
  await page.getByRole("combobox", { name: "Replay step" })
    .selectOption("event");
  for (let index = 0; index < 8; index += 1) {
    await page.getByRole("button", { name: "Previous event" }).click();
  }
  await expect(page).toHaveURL(/record=agent%3A1/);
  await page.getByRole("button", { name: "Ask why" }).click();
  await page.getByRole("textbox", { name: "Question or evidence query" })
    .fill("Why did the agent stop?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("At this moment, no final response was retained."))
    .toBeVisible();
});

test("reconciles cache-aware cost and preserves narrow reachability", async ({
  page,
}, testInfo) => {
  await page.getByRole("tab", { name: "Cost", exact: true }).click();
  await expect(page.getByText("$0.010000")).toBeVisible();
  await expect(page.getByText("$0.003000")).toBeVisible();
  await expect(page.getByText("complete ledger")).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  if (testInfo.project.name === "narrow") {
    const pageSize = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
      viewport: document.documentElement.clientHeight,
    }));
    const playerBounds = await page.getByRole("combobox", { name: "Player" })
      .boundingBox();
    const sessionBounds = await page.getByRole("combobox", { name: "Session" })
      .boundingBox();
    expect(pageSize.scroll).toBeLessThanOrEqual(pageSize.client);
    expect(pageSize.height).toBeGreaterThan(pageSize.viewport);
    expect(playerBounds).not.toBeNull();
    expect(sessionBounds).not.toBeNull();
    expect(playerBounds!.x).toBeGreaterThanOrEqual(0);
    expect(sessionBounds!.x + sessionBounds!.width)
      .toBeLessThanOrEqual(pageSize.client);
  }
});
