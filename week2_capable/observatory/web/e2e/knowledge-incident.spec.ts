import { createHash } from "node:crypto";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { knowledge, mockKnowledge } from "./knowledgeFixture";
import {
  investigation,
  mockRecorded,
  runId,
} from "./recordedFixture";
import { mockRuntime } from "./runtimeFixture";

test.beforeEach(async ({ page }) => {
  await mockRuntime(page);
  await mockRecorded(page);
  await mockKnowledge(page);
});

test("moves from knowledge frontier to exact session evidence", async ({
  page,
}, testInfo) => {
  await page.goto("/?space=knowledge&player=poucet-recorded");
  await expect(page.getByRole("heading", { name: "poucet-recorded" }))
    .toBeVisible();
  await expect(page.getByRole("heading", { name: "Unresolved knowledge" }))
    .toBeVisible();

  await page.getByRole("button", { name: "Truth", exact: true }).click();
  await expect(page.getByText(/Observer truth is comparison-only/)).toBeVisible();
  await expect(page.getByText("Courtyard").first()).toBeVisible();
  await page.getByRole("button", { name: "Diff", exact: true }).click();
  await expect(page.getByText("Newbie Entrance").first()).toBeVisible();
  await expect(page.getByText("White Square").first()).toBeVisible();
  await page.getByRole("button", { name: "Learned", exact: true }).click();
  await page.getByRole("button", { name: "Snapshots" }).click();
  await expect(page.getByRole("button", { name: "Restore" })).toBeDisabled();

  await page.getByRole("button", { name: "Learned map" }).click();
  await expect(page.getByRole("heading", { name: "Learned world" })).toBeVisible();
  await page.getByRole("button", { name: /Temple of Midgaard/ }).click();
  await page.getByRole("button", { name: /title Temple of Midgaard/ }).click();
  const detail = page.getByRole("complementary", {
    name: "Knowledge fact detail",
  });
  await expect(detail.getByText("wire-room-title")).toBeVisible();
  await detail.getByRole("button", { name: /gateway-j2 · seq 2/ }).click();
  await expect(page).toHaveURL(/space=sessions/);
  await expect(page).toHaveURL(/record=gateway%3A2/);
  await expect(page.getByText("gateway record 2", { exact: true })).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  if (testInfo.project.name === "narrow") {
    const size = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(size.scroll).toBeLessThanOrEqual(size.client);
  }
});

test("aggregates a dense learned map before rendering room detail", async ({
  page,
}) => {
  const dense = {
    ...knowledge,
    assertions: Array.from({ length: 180 }, (_, index) => ({
      assertion_id: `room-${index}`,
      fact_id: `room:${index}:title`,
      subject: `room:${index}`,
      predicate: index % 2 === 0 ? "title" : "zone",
      value: index % 2 === 0 ? `Room ${index}` : `Zone ${index % 12}`,
      layer: "learned",
      status: "active",
      confidence: "high",
      current: true,
      conflict_group: null,
      evidence: [{
        session_id: "gateway-j2",
        source_seq: 2,
        wire_digest: `wire-room-${index}`,
        parser_version: "knowledge-1",
        method: "structured-observation",
        observed_at: 1_775_000_000,
      }],
    })),
  };
  await page.route("**/api/players/poucet-recorded/knowledge", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dense),
    });
  });
  await page.goto("/?space=knowledge&player=poucet-recorded&knowledgeLens=map");
  await expect(page.getByText("Aggregated by zone")).toBeVisible();

  const started = Date.now();
  await page.getByRole("button", { name: "rooms", exact: true }).click();
  await expect(page.getByLabel("Learned rooms").getByRole("button"))
    .toHaveCount(120);
  expect(Date.now() - started).toBeLessThan(1_000);
  await expect(page.getByText(/rendering is capped at 120 nodes/)).toBeVisible();

  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await expect(page.getByRole("navigation", { name: "Knowledge views" }))
    .toBeVisible();
  const size = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(size.scroll).toBeLessThanOrEqual(size.client);
});

test("exports annotations and reopens the selected prefix offline", async ({
  page,
}) => {
  await mockIncidentExport(page);
  await page.goto("/?space=sessions&player=poucet-recorded");
  await page.getByRole("button", { name: "Incident", exact: true }).click();
  await page.getByRole("button", { name: "Bookmark" }).click();
  await page.getByRole("textbox", {
    name: "Add context to the selected evidence",
  }).fill("Review why completion was accepted.");
  await page.getByRole("button", { name: "Attach note" }).click();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export capsule" }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();

  const input = page.locator('input[type="file"]');
  await input.setInputFiles(path!);
  await expect(
    page.getByText("Offline · integrity-verified incident capsule"),
  ).toBeVisible();
  await expect(page).toHaveURL(/record=agent%3A6/);
  await expect(page.getByRole("button", { name: "Ask why" })).toHaveCount(0);
  await expect(page.getByText("Integrity verified before opening")).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  let networkRequests = 0;
  await page.route("**/api/**", async (route) => {
    networkRequests += 1;
    await route.abort();
  });
  await page.getByRole("tab", { name: "Evidence" }).click();
  await page.getByRole("tab", { name: "Cost", exact: true }).click();
  await expect(page.getByText("Integrity verified before opening")).toBeVisible();
  await expect(page.getByText("Review why completion was accepted.")).toBeVisible();
  await page.waitForTimeout(2_100);
  expect(networkRequests).toBe(0);
});

async function mockIncidentExport(page: Page) {
  await page.route("**/api/incidents/export", async (route) => {
    const request = route.request().postDataJSON() as {
      selected_record_id: string;
      diagnostic_id: string | null;
      lens: string;
      annotations: unknown[];
    };
    const records = investigation.records.filter(
      (record) => record.id !== "benchmark:outcome",
    );
    const portableInvestigation = {
      ...investigation,
      records,
      diagnostics: [],
      lens: {
        ...investigation.lens,
        truth: {
          state: "missing",
          title: "Verified experiment outcome",
          text: "The selected prefix ends before outcome verification.",
          citations: [],
        },
      },
      capture_gaps: [
        "offline capsule is intentionally limited to its selected prefix",
      ],
    };
    const payload = {
      generated_at: "2026-07-30T12:00:00Z",
      title: "J2 offline incident",
      player_id: investigation.player_id,
      source_versions: { capsule: "2", repository: "fixture" },
      investigation: portableInvestigation,
      knowledge,
      history: {
        player_id: investigation.player_id,
        total_runs: 1,
        successful_runs: 0,
        failed_runs: 1,
        items: [{
          kind: "false_completion",
          runs: 1,
          critical: 1,
          warning: 0,
          notice: 0,
          latest_run: investigation.run.label,
          run_ids: [runId],
        }],
      },
      selection: {
        selected_record_id: request.selected_record_id,
        diagnostic_id: request.diagnostic_id,
        lens: request.lens,
      },
      annotations: request.annotations,
      redaction: {
        policy: "credentials and local paths removed at export",
        replacements: 0,
        local_paths_included: false,
        credentials_included: false,
      },
    };
    const digest = createHash("sha256")
      .update(JSON.stringify(payload))
      .digest("hex");
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.boukensha.incident+json",
      headers: {
        "Content-Disposition": 'attachment; filename="incident.json"',
      },
      body: JSON.stringify({
        kind: "boukensha.observatory.incident",
        version: 2,
        digest,
        payload,
      }),
    });
  });
}
