import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

import { expect, test } from "@playwright/test"

type BrowserMetric = {
  p50_ms: number
  p95_ms: number
  samples: number
}

const readinessPath = fileURLToPath(
  new URL("../../src/dev/backend-readiness.json", import.meta.url)
)
const readiness = JSON.parse(readFileSync(readinessPath, "utf8")) as {
  fixture: { digest_sha256: string }
}

test("production browser validates bounded resources and useful content", async ({
  browser,
  page,
}, testInfo) => {
  const requests: string[] = []
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/")) {
      requests.push(new URL(request.url()).pathname)
    }
  })
  await page.goto("/sessions")
  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible()
  const pageCatalogRequests = requests.filter(
    (path) => path === "/api/v1/sessions"
  ).length
  expect(pageCatalogRequests).toBe(1)

  const result = await page.evaluate(async () => {
    function validateCatalog(value: unknown): asserts value is {
      continuation_cursor: string | null
      sessions: Array<{
        id: string
        projection_status: "available" | "fault" | "pending"
        state: string
      }>
    } {
      if (
        typeof value !== "object" ||
        value === null ||
        !("sessions" in value) ||
        !Array.isArray(value.sessions) ||
        value.sessions.length > 50
      ) {
        throw new Error("catalog failed the browser-visible bounded contract")
      }
    }

    async function catalog(): Promise<{
      duration: number
      payloadBytes: number
    }> {
      const started = performance.now()
      const response = await fetch("/api/v1/sessions?limit=50")
      const body = await response.text()
      const value: unknown = JSON.parse(body)
      validateCatalog(value)
      return {
        duration: performance.now() - started,
        payloadBytes: new TextEncoder().encode(body).byteLength,
      }
    }

    await catalog()
    const samples = []
    let payloadBytes = 0
    // Oxlint disable keeps cache-state samples sequential and independent.
    // oxlint-disable no-await-in-loop
    for (let sample = 0; sample < 20; sample += 1) {
      const measured = await catalog()
      samples.push(measured.duration)
      payloadBytes = measured.payloadBytes
    }
    // oxlint-enable no-await-in-loop
    samples.sort((left, right) => left - right)
    const p50 = (samples[9] + samples[10]) / 2
    const p95 = samples[Math.ceil(samples.length * 0.95) - 1]
    const navigationEntries = performance.getEntriesByType("navigation").length
    return {
      metric: {
        p50_ms: p50,
        p95_ms: p95,
        samples: samples.length,
      },
      navigationEntries,
      payloadBytes,
    }
  })

  expect(result.metric.samples).toBe(20)
  expect(result.payloadBytes).toBeLessThan(64 * 1024)
  expect(result.navigationEntries).toBe(1)
  expect(requests.filter((path) => path === "/api/v1/sessions")).toHaveLength(
    22
  )
  await testInfo.attach("browser-readiness.json", {
    body: Buffer.from(
      JSON.stringify(
        {
          browser: testInfo.project.name,
          browser_version: browser.version(),
          cache_state: "warm_after_one_excluded_warmup",
          catalog: result.metric satisfies BrowserMetric,
          document_reloads: result.navigationEntries - 1,
          fixture_digest_sha256: readiness.fixture.digest_sha256,
          measurement_layer: "fetch_text_parse_validate",
          node: process.version,
          page_catalog_requests: pageCatalogRequests,
          payload_bytes: result.payloadBytes,
          platform: {
            architecture: process.arch,
            system: process.platform,
          },
          playwright: "1.62.1",
          measured_request_count: 21,
          total_catalog_requests: 22,
          viewport: testInfo.project.use.viewport,
        },
        null,
        2
      )
    ),
    contentType: "application/json",
  })
})

test("stopped session makes no recurring browser request", async ({ page }) => {
  const stoppedRequests: string[] = []
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/sessions/session-001")) {
      stoppedRequests.push(request.url())
    }
  })
  await page.goto("/sessions")
  const status = await page.evaluate(async () => {
    // Oxlint disable preserves the bounded materialization retry protocol.
    // oxlint-disable no-await-in-loop
    for (let attempt = 0; attempt < 2_000; attempt += 1) {
      const response = await fetch("/api/v1/sessions/session-001")
      if (response.status !== 202) {
        const value = (await response.json()) as { state: string }
        return value.state
      }
      await new Promise((resolve) => setTimeout(resolve, 0))
    }
    // oxlint-enable no-await-in-loop
    throw new Error("stopped session did not become readable")
  })
  await page.waitForTimeout(250)

  expect(status).toBe("stopped")
  const countAtReady = stoppedRequests.length
  await page.waitForTimeout(250)
  expect(stoppedRequests).toHaveLength(countAtReady)
})
