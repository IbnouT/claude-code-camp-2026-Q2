import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { mockLiveFidelity } from "./liveFidelityFixture";
import { mockRecordedFidelity } from "./recordedFixture";
import { mockRuntime } from "./runtimeFixture";

const captureDirectory = resolve("captures/mock-fidelity");

type VisualSignature = {
  height: number;
  width: number;
  fontFamily: string;
  fontSize: string;
  fontWeight: string;
  lineHeight: string;
  padding: string;
  gap: string;
  margin: string;
  letterSpacing: string;
  textTransform: string;
  color: string;
  backgroundColor: string;
  backgroundImage: string;
  borderTop: string;
  borderRight: string;
  borderBottom: string;
  borderLeft: string;
  borderRadius: string;
  boxShadow: string;
};

async function visualSignature(
  page: import("@playwright/test").Page,
  selector: string,
): Promise<VisualSignature> {
  return page.locator(selector).first().evaluate((element) => {
    const style = getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    return {
      height: Math.round(bounds.height),
      width: Math.round(bounds.width),
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      lineHeight: style.lineHeight,
      padding: style.padding,
      gap: style.gap,
      margin: style.margin,
      letterSpacing: style.letterSpacing,
      textTransform: style.textTransform,
      color: style.color,
      backgroundColor: style.backgroundColor,
      backgroundImage: style.backgroundImage,
      borderTop: style.borderTop,
      borderRight: style.borderRight,
      borderBottom: style.borderBottom,
      borderLeft: style.borderLeft,
      borderRadius: style.borderRadius,
      boxShadow: style.boxShadow,
    };
  });
}

type TimelineSignature = {
  markers: Array<{
    backgroundColor: string;
    height: number;
    leftPercent: number;
    small: boolean;
    width: number;
  }>;
  labels: Array<{
    leftPercent: number;
    text: string;
  }>;
  cursorLeftPercent: number;
};

async function timelineSignature(
  page: import("@playwright/test").Page,
  trackSelector: string,
  markerSelector: string,
  cursorSelector: string,
): Promise<TimelineSignature> {
  return page.locator(trackSelector).evaluate(
    (track, selectors) => {
      const bounds = track.getBoundingClientRect();
      const percent = (element: Element) => {
        const child = element.getBoundingClientRect();
        return Math.round(
          (((child.left + child.width / 2) - bounds.left) / bounds.width)
          * 1_000,
        ) / 10;
      };
      const markers = Array.from(
        track.querySelectorAll(selectors.markerSelector),
      ).map((element) => {
        const markerBounds = element.getBoundingClientRect();
        return {
          backgroundColor: getComputedStyle(element).backgroundColor,
          height: Math.round(markerBounds.height),
          leftPercent: percent(element),
          small: element.classList.contains("small"),
          width: Math.round(markerBounds.width),
        };
      });
      const labels = Array.from(track.querySelectorAll(".tlab")).map(
        (element) => ({
          leftPercent: percent(element),
          text: element.textContent?.trim() ?? "",
        }),
      );
      const cursor = track.querySelector(selectors.cursorSelector);
      if (!cursor) throw new Error("Timeline cursor is missing");
      return {
        markers,
        labels,
        cursorLeftPercent: percent(cursor),
      };
    },
    { markerSelector, cursorSelector },
  );
}

function expectTimelineMatches(
  built: TimelineSignature,
  approved: TimelineSignature,
) {
  expect.soft(built.markers).toHaveLength(approved.markers.length);
  for (const [index, marker] of approved.markers.entries()) {
    const builtMarker = built.markers[index];
    expect.soft(
      builtMarker && {
        ...builtMarker,
        leftPercent: undefined,
      },
      `Timeline marker ${index + 1} must preserve its approved role.`,
    ).toEqual({
      ...marker,
      leftPercent: undefined,
    });
    expect.soft(
      Math.abs((builtMarker?.leftPercent ?? Number.NaN) - marker.leftPercent),
      `Timeline marker ${index + 1} must stay within one integer-sequence `
        + "step of its approved position.",
    ).toBeLessThanOrEqual(1.1);
  }

  expect.soft(built.labels).toHaveLength(approved.labels.length);
  for (const [index, label] of approved.labels.entries()) {
    const builtLabel = built.labels[index];
    expect.soft(
      builtLabel?.text,
      `Timeline label ${index + 1} must preserve its approved meaning.`,
    ).toBe(label.text);
    expect.soft(
      Math.abs((builtLabel?.leftPercent ?? Number.NaN) - label.leftPercent),
      `Timeline label ${index + 1} must follow its evidence marker.`,
    ).toBeLessThanOrEqual(1.1);
  }
  expect.soft(built.cursorLeftPercent).toBe(approved.cursorLeftPercent);
}

test("captures the Live mock and bound screen at the same viewport", async ({
  browser,
  page,
}) => {
  test.skip(
    test.info().project.name !== "desktop",
    "The first Live direction proof uses the approved 1440 × 900 viewport.",
  );
  await mkdir(captureDirectory, { recursive: true });

  const mockPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await mockPage.goto("http://127.0.0.1:8790/live_cockpit.html");
  await expect(mockPage.locator(".app")).toBeVisible();
  const mockImage = (await mockPage.screenshot({
    path: resolve(captureDirectory, "live_cockpit-mock-1440x900.png"),
  })).toString("base64");

  await mockLiveFidelity(page);
  await page.goto(
    "/?space=live&player=poucet&liveSession=session-live-fidelity",
  );
  await expect(page.locator(".live-cockpit")).toBeVisible();
  await expect(page.locator(".live-cockpit .combat")).toBeVisible();
  await expect(page.locator(".live-cockpit .rail")).toBeVisible();
  await expect(
    page.locator(".live-cockpit").getByText("Turn 47 / iteration 47", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.locator(".live-cockpit").getByText("Zone Midgaard", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.locator(".live-cockpit").getByText("Agent intends", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.locator(".live-cockpit").getByText("Moving east", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".live-cockpit").getByText("Agent iteration 44", {
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.locator(".live-cockpit").getByText("▲ LEVEL UP: now level 4", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".live-cockpit .thought")).toContainText(
    "A kobold blocks the alley east. I'll fight through: the minotaur lair should be past Back Street.",
  );
  await expect(page.locator(".live-cockpit .combat")).toContainText(
    "In combat: a large kobold",
  );
  await expect(page.locator(".live-cockpit .combat")).toContainText(
    "exchange 3 · since turn 46",
  );
  const builtImage = (await page.screenshot({
    path: resolve(captureDirectory, "live_cockpit-built-1440x900.png"),
  })).toString("base64");

  const pairs = [
    [".stage", ".live-cockpit .stage"],
    [".chip", ".live-cockpit .chip"],
    ['.tool[title="Zoom in"]', '.live-cockpit .tool[title="Zoom in"]'],
    [".combat", ".live-cockpit .combat"],
    [".legend", ".live-cockpit .legend"],
    ["aside", ".live-cockpit .rail"],
    [".card", ".live-cockpit .card"],
    [".card h4", ".live-cockpit .card h4"],
    [".stat", ".live-cockpit .stat"],
    [".stat .k", ".live-cockpit .stat .k"],
    [".stat .v", ".live-cockpit .stat .v"],
    [".spine", ".live-cockpit .spine"],
    [".sh small", ".live-cockpit .sh small"],
    [".ev", ".live-cockpit .ev"],
    [".track .cur", ".live-cockpit .cursor"],
    [".compose input", ".live-cockpit .compose input"],
    [".quick span", ".live-cockpit .quick button"],
  ] as const;
  for (const [mockSelector, builtSelector] of pairs) {
    const builtSignature = await visualSignature(page, builtSelector);
    const mockSignature = await visualSignature(mockPage, mockSelector);
    expect.soft(
      { ...builtSignature, width: undefined },
      `${builtSelector} must match ${mockSelector}`,
    ).toEqual({ ...mockSignature, width: undefined });
  }

  const mockTimeline = await timelineSignature(
    mockPage,
    ".track",
    ".ev",
    ".cur",
  );
  const builtTimeline = await timelineSignature(
    page,
    ".live-cockpit .track",
    ".ev",
    ".cursor",
  );
  expectTimelineMatches(builtTimeline, mockTimeline);

  const comparison = await browser.newPage({
    viewport: { width: 2880, height: 950 },
  });
  await comparison.setContent(comparisonDocument(
    "Approved Live mock",
    mockImage,
    "Bound React Live screen",
    builtImage,
  ));
  await comparison.screenshot({
    path: resolve(captureDirectory, "live_cockpit-comparison.png"),
  });
  await comparison.close();
  await mockPage.close();
});

test("captures the Sessions mock and bound screen at the same viewport", async ({
  browser,
  page,
}) => {
  test.skip(
    test.info().project.name !== "desktop",
    "The first direction proof uses the approved 1440 × 900 desktop viewport.",
  );
  await mkdir(captureDirectory, { recursive: true });

  const mockPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await mockPage.goto("http://127.0.0.1:8790/sessions_unified.html");
  await expect(mockPage.locator(".app")).toBeVisible();
  const mockImage = (await mockPage.screenshot({
    path: resolve(captureDirectory, "sessions_unified-mock-1440x900.png"),
  })).toString("base64");

  const retainedRun = process.env.OBSERVATORY_FIDELITY_RUN;
  if (retainedRun) {
    const player = process.env.OBSERVATORY_FIDELITY_PLAYER ?? "direct-full";
    const record = process.env.OBSERVATORY_FIDELITY_RECORD;
    const query = new URLSearchParams({
      space: "sessions",
      player,
      run: retainedRun,
    });
    if (record) query.set("record", record);
    await page.goto(`/?${query.toString()}`);
  } else {
    await page.route("**/api/capabilities", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          version: 1,
          sources: [],
          features: [
            "live",
            "replay",
            "time-travel",
            "diagnostics",
            "query",
          ],
        }),
      });
    });
    await mockRuntime(page);
    await mockRecordedFidelity(page);
    await page.goto("/?space=sessions&record=agent%3Aplan");
  }
  await expect(
    page.getByRole("region", { name: "Sessions investigation" }),
  ).toBeVisible();
  await expect(
    page.locator(".sessions-unified .sync"),
  ).toContainText("Iteration 2 · Turn 18 · The Temple Of Midgaard");
  await expect(
    page.locator(".sessions-unified .iter:has(.ihead.sel)"),
  ).toContainText("Plan");
  await expect(
    page.locator(".sessions-unified .iter:has(.ihead.sel)"),
  ).toContainText("Model call");
  await expect(
    page.locator(".sessions-unified .iter:has(.ihead.sel)"),
  ).toContainText('plan_route(destination: "bakery")');
  await expect(
    page.locator(".sessions-unified .ihead svg").first(),
  ).toBeVisible();
  const builtImage = (await page.screenshot({
    path: resolve(captureDirectory, "sessions_unified-built-1440x900.png"),
  })).toString("base64");

  const pairs = [
    [".app > header", ".canonical-header"],
    [".subbar", ".sessions-unified .subbar"],
    [".sync", ".sessions-unified .sync"],
    [".body", ".sessions-unified .body"],
    [".pane.map", ".sessions-unified .pane.map"],
    [".replay", ".sessions-unified .replay"],
    [".brand", ".brand"],
    ["nav a.on", ".space-link[aria-current='page']"],
    [".subbar h2", ".sessions-unified .subbar h2"],
    [".meters", ".sessions-unified .meters"],
    [".switch", ".sessions-unified .switch"],
    [".ph", ".sessions-unified .ph"],
    [".ihead", ".sessions-unified .ihead"],
    [".ihead .ttl", ".sessions-unified .ihead .ttl"],
    [".step.kplan .lbl", ".sessions-unified .step.kplan .lbl"],
    [".step.kmodel .lbl", ".sessions-unified .step.kmodel .lbl"],
    [".step.ktool .lbl", ".sessions-unified .step.ktool .lbl"],
    [".deep a", ".sessions-unified .deep button"],
    [".rmeta", ".sessions-unified .rmeta"],
    [".opendetail", ".sessions-unified .opendetail"],
  ] as const;
  for (const [mockSelector, builtSelector] of pairs) {
    const builtSignature = await visualSignature(page, builtSelector);
    const mockSignature = await visualSignature(mockPage, mockSelector);
    const ignoreFlexibleMargin = builtSelector === ".sessions-unified .switch";
    expect.soft(
      {
        ...builtSignature,
        width: undefined,
        margin: ignoreFlexibleMargin ? undefined : builtSignature.margin,
      },
      `${builtSelector} must match ${mockSelector}`,
    ).toEqual({
      ...mockSignature,
      width: undefined,
      margin: ignoreFlexibleMargin ? undefined : mockSignature.margin,
    });
  }

  const comparison = await browser.newPage({
    viewport: { width: 2880, height: 950 },
  });
  await comparison.setContent(`
    <!doctype html>
    <html>
      <head>
        <style>
          * { box-sizing: border-box; }
          html, body { width: 2880px; height: 950px; margin: 0; overflow: hidden; }
          body { display: grid; grid-template-columns: 1fr 1fr; background: #080b0f; }
          figure { margin: 0; }
          figcaption {
            height: 50px; display: grid; place-items: center;
            color: #edf4f8; background: #0d1218;
            font: 600 18px Inter, system-ui, sans-serif;
            letter-spacing: .08em; text-transform: uppercase;
          }
          img { width: 1440px; height: 900px; display: block; }
          figure + figure { border-left: 2px solid #68e1dc; }
        </style>
      </head>
      <body>
        <figure>
          <figcaption>Approved mock</figcaption>
          <img alt="Approved Sessions mock" src="data:image/png;base64,${mockImage}">
        </figure>
        <figure>
          <figcaption>Bound React screen</figcaption>
          <img alt="Built Sessions screen" src="data:image/png;base64,${builtImage}">
        </figure>
      </body>
    </html>
  `);
  await comparison.screenshot({
    path: resolve(captureDirectory, "sessions_unified-comparison.png"),
  });
  await comparison.close();
  await mockPage.close();
});

function comparisonDocument(
  leftLabel: string,
  leftImage: string,
  rightLabel: string,
  rightImage: string,
) {
  return `
    <!doctype html>
    <html>
      <head>
        <style>
          * { box-sizing: border-box; }
          html, body { width: 2880px; height: 950px; margin: 0; overflow: hidden; }
          body { display: grid; grid-template-columns: 1fr 1fr; background: #080b0f; }
          figure { margin: 0; }
          figcaption {
            height: 50px; display: grid; place-items: center;
            color: #edf4f8; background: #0d1218;
            font: 600 18px Inter, system-ui, sans-serif;
            letter-spacing: .08em; text-transform: uppercase;
          }
          img { width: 1440px; height: 900px; display: block; }
          figure + figure { border-left: 2px solid #68e1dc; }
        </style>
      </head>
      <body>
        <figure>
          <figcaption>${leftLabel}</figcaption>
          <img alt="${leftLabel}" src="data:image/png;base64,${leftImage}">
        </figure>
        <figure>
          <figcaption>${rightLabel}</figcaption>
          <img alt="${rightLabel}" src="data:image/png;base64,${rightImage}">
        </figure>
      </body>
    </html>
  `;
}
