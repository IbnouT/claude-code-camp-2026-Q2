import { expect, test, type Page } from "@playwright/test";
import { mockRecorded } from "./recordedFixture";
import { mockRuntime } from "./runtimeFixture";
import { mockExperiment } from "./experimentFixture";
import { mockKnowledge } from "./knowledgeFixture";

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

test("captures the B6 grounded investigation flow", async ({
  page,
}, testInfo) => {
  await renderFixture(page);
  await mockRuntime(page);
  await mockRecorded(page);
  await page.goto("/?space=sessions");
  await page.getByRole("button", { name: "Ask why" }).click();
  await page.getByRole("textbox", { name: "Question or evidence query" })
    .fill("Why did the agent stop?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Validated query")).toBeVisible();
  await expect(page.getByText("Exact evidence")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b6-grounded-query-dark.png"),
    fullPage: false,
  });
});

test("captures the B5 Experiments workbench for rendered review", async ({
  page,
}, testInfo) => {
  await renderFixture(page);
  await mockRuntime(page);
  await mockExperiment(page);
  await page.goto("/?space=experiments");
  await expect(
    page.getByRole("heading", { name: "Model-facing result rendering" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b5-experiments-compare-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Definition", exact: true }).click();
  await expect(page.getByText("Six stop criteria")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b5-experiments-definition-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run queue" }).click();
  await page.getByRole("button", { name: "Validate effective definition" }).click();
  await expect(page.getByRole("status")).toContainText("Validation passed");
  await page.screenshot({
    path: testInfo.outputPath("b5-experiments-run-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Counterfactual replay" }).click();
  await expect(page.getByText(/cannot claim how the agent would have behaved/))
    .toBeVisible();
  await page.getByRole("button", { name: "Use light theme" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b5-experiments-replay-light.png"),
    fullPage: true,
  });
});

test("captures the B7 Knowledge and incident workflow", async ({
  page,
}, testInfo) => {
  await renderFixture(page);
  await mockRuntime(page);
  await mockRecorded(page);
  await mockKnowledge(page);
  await page.goto("/?space=knowledge&player=poucet-recorded");
  await expect(page.getByRole("heading", { name: "Unresolved knowledge" }))
    .toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-overview-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Learned map" }).click();
  await page.getByRole("button", { name: /Temple of Midgaard/ }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-map-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Entities" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-entities-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Progression" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-progression-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Snapshots" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-snapshots-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "History" }).click();
  await page.getByRole("button", { name: "Use light theme" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-history-light.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Sessions" }).click();
  await page.getByRole("tab", { name: /Diagnostics/ }).click();
  await expect(page.getByRole("heading", { name: "Diagnostic history" }))
    .toBeVisible();
  await page.getByRole("button", { name: "Incident", exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-incident-workflow-light.png"),
    fullPage: true,
  });
});
