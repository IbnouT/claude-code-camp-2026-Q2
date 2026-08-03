import { fileURLToPath } from "node:url"

import { defineConfig, devices } from "@playwright/test"

const webRoot = fileURLToPath(new URL(".", import.meta.url))
const backendRoot = fileURLToPath(new URL("../backend", import.meta.url))
const browserPort = 4175
const baseURL = `http://127.0.0.1:${browserPort}`

export default defineConfig({
  testDir: "./tests/readiness",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "on-first-retry",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: [
      `cd "${backendRoot}" && uv run`,
      "python -m tests.readiness.server",
      `--web-dist "${webRoot}dist"`,
      `--port ${browserPort}`,
    ].join(" "),
    url: `${baseURL}/api/v1/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
