import { expect, test, type Page } from "@playwright/test";
import { mockRecorded } from "./recordedFixture";
import { mockRuntime } from "./runtimeFixture";
import { mockExperimentFidelity } from "./experimentFixture";
import { mockKnowledge } from "./knowledgeFixture";
import { mockLiveFidelity } from "./liveFidelityFixture";

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
  await mockExperimentFidelity(page);
  await page.goto("/?space=experiments");
  await expect(
    page.getByRole("heading", { name: "Rendering × tool surface" }),
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
  await expect(page.getByRole("region", { name: "Player knowledge" }))
    .toBeVisible();
  await expect(page.getByRole("button", { name: "Learned map" }))
    .toHaveAttribute("aria-current", "page");
  for (const lens of ["Entities", "Progression", "Milestones"]) {
    await expect(page.getByRole("button", { name: lens })).toBeVisible();
  }
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-map-dark.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: /Temple of Midgaard/ }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-map-selection-dark.png"),
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

  await page.getByRole("button", { name: "Milestones" }).click();
  await page.screenshot({
    path: testInfo.outputPath("b7-knowledge-milestones-dark.png"),
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

test("full-mode cockpit gate: Grow, Focus and Lantern with a selected room", async ({
  page,
}, testInfo) => {
  await renderFixture(page);
  await mockLiveFidelity(page);
  await page.goto("/?room=room-back-street");
  await expect(page.getByRole("region", { name: "Live cockpit" }))
    .toBeVisible();
  for (const mode of ["Grow", "Focus", "Lantern"]) {
    await page
      .getByRole("group", { name: "Map mode" })
      .getByRole("button", { name: mode })
      .click();
    await page.waitForTimeout(250);
    /* the thought callout and the selected-room popover must remain inside
       the visible stage after each mode transform (edge-clamp gate) */
    const stage = await page.locator(".live-cockpit svg.map").boundingBox();
    if (mode === "Grow") {
      await expect(
        page.getByText("Learned world 22 rooms · 5 frontier", { exact: true }),
      ).toBeVisible();
      await expect(page.locator(".live-cockpit .roomnode")).toHaveCount(22);
      const frontier = page.locator(
        '.live-cockpit svg.map rect[stroke="#26374b"][stroke-dasharray]',
      );
      await expect(frontier).toHaveCount(5);
      if (stage) {
        for (const [index, box] of (
          await frontier.evaluateAll((elements) =>
            elements.map((element) => {
              const bounds = element.getBoundingClientRect();
              return {
                x: bounds.x,
                y: bounds.y,
                width: bounds.width,
                height: bounds.height,
              };
            })
          )
        ).entries()) {
          expect(box.x, `frontier ${index + 1} left edge in Grow`)
            .toBeGreaterThanOrEqual(stage.x - 1);
          expect(box.x + box.width, `frontier ${index + 1} right edge in Grow`)
            .toBeLessThanOrEqual(stage.x + stage.width + 1);
          expect(box.y, `frontier ${index + 1} top edge in Grow`)
            .toBeGreaterThanOrEqual(stage.y - 1);
          expect(box.y + box.height, `frontier ${index + 1} bottom edge in Grow`)
            .toBeLessThanOrEqual(stage.y + stage.height + 1);
        }
      }
    }
    for (const part of [".live-cockpit .thought", ".live-cockpit .roompop"]) {
      const box = await page.locator(part).boundingBox();
      expect(box, `${part} missing in ${mode}`).not.toBeNull();
      if (box && stage) {
        expect(box.x, `${part} left edge in ${mode}`)
          .toBeGreaterThanOrEqual(stage.x - 1);
        expect(box.x + box.width, `${part} right edge in ${mode}`)
          .toBeLessThanOrEqual(stage.x + stage.width + 1);
        expect(box.y, `${part} top edge in ${mode}`)
          .toBeGreaterThanOrEqual(stage.y - 1);
        expect(box.y + box.height, `${part} bottom edge in ${mode}`)
          .toBeLessThanOrEqual(stage.y + stage.height + 1);
      }
    }
    const controls = await page.locator(".live-cockpit .stagetools").boundingBox();
    const popover = await page.locator(".live-cockpit .roompop").boundingBox();
    if (controls && popover) {
      const overlapWidth = Math.max(
        0,
        Math.min(controls.x + controls.width, popover.x + popover.width)
          - Math.max(controls.x, popover.x),
      );
      const overlapHeight = Math.max(
        0,
        Math.min(controls.y + controls.height, popover.y + popover.height)
          - Math.max(controls.y, popover.y),
      );
      expect(
        overlapWidth * overlapHeight,
        `selected-room popover must not cover stage controls in ${mode}`,
      ).toBe(0);
    }
    /* overlay-safe collisions: the beacon label stays clear of the control
       band, and the thought callout never covers the beacon label */
    const rectOverlap = (
      a: { x: number; y: number; width: number; height: number },
      b: { x: number; y: number; width: number; height: number },
    ): number => {
      const w = Math.max(
        0,
        Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x),
      );
      const h = Math.max(
        0,
        Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y),
      );
      return w * h;
    };
    const beaconLabel = await page.getByText(/known location/).first()
      .boundingBox();
    const stagehead = await page.locator(".live-cockpit .stagehead")
      .boundingBox();
    const thought = await page.locator(".live-cockpit .thought").boundingBox();
    if (beaconLabel) {
      for (const [name, region] of [
        ["stagehead", stagehead],
        ["stagetools", controls],
      ] as const) {
        if (region) {
          expect(
            rectOverlap(beaconLabel, region),
            `beacon label under ${name} in ${mode}`,
          ).toBe(0);
        }
      }
      if (thought) {
        expect(
          rectOverlap(beaconLabel, thought),
          `thought covers beacon label in ${mode}`,
        ).toBe(0);
      }
    }
    await page.screenshot({
      path: testInfo.outputPath(`live-mode-${mode.toLowerCase()}-selected.png`),
      fullPage: true,
    });
  }
});
